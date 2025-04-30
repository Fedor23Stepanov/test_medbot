# bot/handlers.py

import re
import asyncio
from functools import partial

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ContextTypes,
    MessageHandler, CallbackQueryHandler,
    filters, CommandHandler, Application
)

from db.crud import (
    invite_user,
    get_user_by_tg, get_user_by_id,
    activate_user,
    block_user_by_username,
    get_random_device,
    create_event,
    create_proxy_log,
    get_user_stats,
    list_active_users,
)
from crawler.redirector import fetch_redirect, ProxyAcquireError
from config import INITIAL_ADMINS
from db.models import UserStatus

URL_PATTERN = re.compile(r'https?://[^\s)]+')


# -------------- ВСПОМОГАТЕЛЬ: меню ---------------

def build_main_menu(role: str) -> ReplyKeyboardMarkup:
    base = [["📊 Статистика", "⚙️ Настройки"]]
    if role in ("Maintainer", "Admin"):
        base.append(["👥 Пользователи", "➕ Добавить пользователя"])
    return ReplyKeyboardMarkup(base, resize_keyboard=True)


async def show_main_menu(update: Update, *, role: str):
    kb = build_main_menu(role)
    await update.message.reply_text("🧾 Меню Бота", reply_markup=kb)


# -------------- /start и /menu ---------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    username = (update.effective_user.username or "").strip().lstrip("@").lower()

    user = await get_user_by_tg(tg_id)
    if user:
        if user.status is UserStatus.blocked:
            return  # игнорируем
        if user.status is UserStatus.active:
            return await show_main_menu(update, role=user.role)

    # попытка активации pending-пользователя
    activated = await activate_user(tg_id, username)
    if activated:
        return await show_main_menu(update, role=activated.role)

    # нет доступа
    await update.message.reply_text(
        "❌ У тебя нет доступа. Обратись к администратору.",
        reply_markup=ReplyKeyboardRemove()
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active:
        return
    await show_main_menu(update, role=user.role)


# -------------- Статистика ---------------

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active:
        return
    st = await get_user_stats(user.id)
    text = (
        f"📊 Ваша статистика:\n"
        f"• За всё время: {st['all_time']}\n"
        f"• За последний месяц: {st['last_month']}\n"
        f"• За последнюю неделю: {st['last_week']}"
    )
    await update.message.reply_text(text, reply_markup=build_main_menu(user.role))


# -------------- Пользователи (для модеров/админов) ---------------

async def users_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active or user.role not in ("Maintainer", "Admin"):
        return

    all_users = await list_active_users()
    kb = [
        [InlineKeyboardButton(f"@{u.username}", callback_data=f"user_{u.id}")]
        for u in all_users
    ]
    await update.message.reply_text(
        "👥 Список пользователей:", 
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def user_detail_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, uid = q.data.split("_", 1)
    target = await get_user_by_id(int(uid))
    if not target:
        return await q.edit_message_text("Пользователь не найден.")

    st = await get_user_stats(target.id)
    text = (
        f"👤 @{target.username}\n"
        f"Роль: {target.role}\n\n"
        f"📊 Статистика:\n"
        f"• Всего: {st['all_time']}\n"
        f"• Месяц: {st['last_month']}\n"
        f"• Неделя: {st['last_week']}"
    )
    kb = [[InlineKeyboardButton("⛔️ Заблокировать", callback_data=f"block_{target.id}")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def block_user_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, uid = q.data.split("_", 1)
    target = await get_user_by_id(int(uid))
    if target:
        await block_user_by_username(target.username)
        await q.edit_message_text(f"❌ @{target.username} заблокирован.")
    else:
        await q.edit_message_text("Пользователь не найден.")


# -------------- Добавить пользователя через кнопку ---------------

async def start_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active or user.role not in ("Maintainer", "Admin"):
        return
    context.user_data["awaiting_new_username"] = True
    await update.message.reply_text(
        "Введите ник нового пользователя (без @):",
        reply_markup=ReplyKeyboardRemove()
    )


#  как только приходит текст — либо это ник нового юзера, либо ссылка:
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    text = update.message.text.strip()

    # 1) Если ждём ник для /add через меню
    if context.user_data.get("awaiting_new_username"):
        uname = text.lstrip("@").lower()
        new = await invite_user(username=uname, role="User", invited_by=tg_id)
        context.user_data.pop("awaiting_new_username", None)
        await update.message.reply_text(
            f"Пользователь @{new.username} приглашён. Статус: {new.status}.",
            reply_markup=build_main_menu((await get_user_by_tg(tg_id)).role)
        )
        return

    # 2) Проверяем обычную клавиатуру-меню
    if text == "📊 Статистика":
        return await stats_cmd(update, context)
    if text == "👥 Пользователи":
        return await users_list_cmd(update, context)
    if text == "➕ Добавить пользователя":
        return await start_add_user(update, context)
    if text == "🧾 Меню Бота":
        return await menu(update, context)

    # 3) остальной код — обработка ссылок
    user = await get_user_by_tg(tg_id)
    if not user or user.status is not UserStatus.active:
        return
    urls = URL_PATTERN.findall(text)
    if not urls:
        await create_event(user_id=user.id, state="no link",
                           device_option_id=0, initial_url="", final_url="",
                           ip=None, isp=None)
        return await update.message.reply_text(
            "❗ Пожалуйста, пришли одну ссылку.",
            reply_to_message_id=update.message.message_id
        )
    if len(urls) > 1:
        await create_event(user_id=user.id, state="many links",
                           device_option_id=0, initial_url="", final_url="",
                           ip=None, isp=None)
        return await update.message.reply_text(
            "❗ Одну ссылку за раз, пожалуйста.",
            reply_to_message_id=update.message.message_id
        )

    raw_url = urls[0]
    try:
        device = await get_random_device()
    except ValueError as e:
        return await update.message.reply_text(
            str(e),
            reply_to_message_id=update.message.message_id
        )

    loop = asyncio.get_running_loop()
    try:
        initial_url, final_url, ip, isp, _, proxy_attempts = await loop.run_in_executor(
            None, partial(fetch_redirect, raw_url, device)
        )
    except ProxyAcquireError as e:
        for at in e.attempts:
            await create_proxy_log(at["attempt"], at["ip"], at["city"])
        await create_event(
            user_id=user.id, state="proxy error",
            device_option_id=device["id"], initial_url=raw_url,
            final_url="", ip=None, isp=None
        )
        return await update.message.reply_text(
            f"⚠️ Не удалось подобрать прокси за {len(e.attempts)} попыток.",
            reply_to_message_id=update.message.message_id
        )
    for at in proxy_attempts:
        await create_proxy_log(at["attempt"], at["ip"], at["city"])
    await create_event(
        user_id=user.id, state="success",
        device_option_id=device["id"],
        initial_url=initial_url, final_url=final_url,
        ip=ip, isp=isp
    )

    report = (
        f"📱 Профиль: {device['model']}\n"
        f"   • UA: {device['ua']}\n"
        f"🔗 Начальный URL:\n{initial_url}\n"
        f"✅ Итоговый URL:\n{final_url}\n"
        f"🌐 IP: {ip}\n"
        f"📡 ISP: {isp}"
    )
    await update.message.reply_text(
        report,
        disable_web_page_preview=True,
        reply_to_message_id=update.message.message_id
    )


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    # inline callbacks
    app.add_handler(CallbackQueryHandler(user_detail_cb, pattern=r"^user_\d+$"))
    app.add_handler(CallbackQueryHandler(block_user_cb, pattern=r"^block_\d+$"))
    # reply-кнопки и ссылки
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
