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
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CommandHandler,
    Application
)

from db.crud import (
    get_user_by_tg,
    get_user_by_id,           # ← вместо get_user_by_tg для внутренних id
    activate_user,
    invite_user,
    list_pending_users,        # ← возвращает User.status==pending (с опцией invited_by)
    revoke_invitation,
    get_user_stats,
    get_random_device,
    create_event,
    create_proxy_log,
)
from crawler.redirector import fetch_redirect, ProxyAcquireError
from db.models import UserStatus

URL_PATTERN = re.compile(r'https?://[^\s)]+')


# ——— Помощники по меню —————————————————————————————

def build_main_menu(role: str) -> ReplyKeyboardMarkup:
    kb = [["📊 Статистика", "⚙️ Настройки"]]
    if role in ("Maintainer", "Admin"):
        kb.append(["👥 Пользователи", "➕ Добавить пользователя"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


async def show_main_menu(update: Update, role: str):
    await update.message.reply_text("🧾 Меню бота", reply_markup=build_main_menu(role))


# ——— /start и /menu ————————————————————————————————

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id   = update.effective_user.id
    username = (update.effective_user.username or "").strip().lstrip("@").lower()

    user = await get_user_by_tg(tg_id)
    if user and user.status is UserStatus.active:
        return await show_main_menu(update, role=user.role)
    if user and user.status is UserStatus.blocked:
        return  # игнорируем

    activated = await activate_user(tg_id, username)
    if activated:
        return await show_main_menu(update, role=activated.role)

    await update.message.reply_text(
        "❌ У тебя нет доступа. Обратись к администратору.",
        reply_markup=ReplyKeyboardRemove()
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if user and user.status is UserStatus.active:
        await show_main_menu(update, role=user.role)


# ——— Статистика ——————————————————————————————————

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active:
        return
    st = await get_user_stats(user.id)
    text = (
        f"📊 Твоя статистика:\n"
        f"• За всё время: {st['all_time']}\n"
        f"• За последний месяц: {st['last_month']}\n"
        f"• За последнюю неделю: {st['last_week']}"
    )
    await update.message.reply_text(text, reply_markup=build_main_menu(user.role))


# ——— Список приглашённых (pending) —————————————————————

async def users_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active or user.role not in ("Maintainer", "Admin"):
        return

    # у модера — только свои, у админа — все приглашённые
    pendings = (
        await list_pending_users()
        if user.role == "Admin"
        else await list_pending_users(invited_by=user.tg_id)
    )

    if not pendings:
        return await update.message.reply_text(
            "Нет активных приглашений.",
            reply_markup=build_main_menu(user.role)
        )

    buttons = []
    for u in pendings:
        # эмоджи статуса
        emoji = {"pending":"⏳","active":"✅","blocked":"⛔️"}[u.status.value]
        buttons.append([
            InlineKeyboardButton(f"@{u.username} {emoji}", callback_data=f"invite_{u.id}")
        ])

    await update.message.reply_text(
        "👥 Приглашённые пользователи:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def invite_detail_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, uid = q.data.split("_", 1)
    target = await get_user_by_id(int(uid))
    if not target:
        return await q.edit_message_text("Пользователь не найден.")

    emoji = {
        "pending":"⏳ Ожидает",
        "active":"✅ Активирован",
        "blocked":"⛔️ Заблокирован"
    }[target.status.value]
    text = f"@{target.username}\nСтатус: {emoji}"
    kb = [[InlineKeyboardButton("🗑️ Отозвать приглашение", callback_data=f"revoke_{target.id}")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def revoke_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, uid = q.data.split("_", 1)
    ok = await revoke_invitation(int(uid))
    await q.edit_message_text(
        "✅ Приглашение отозвано." if ok else "❌ Не удалось отозвать."
    )


# ——— Режим «Добавить пользователя» ————————————————————

async def start_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active or user.role not in ("Maintainer","Admin"):
        return
    context.user_data["awaiting_new_username"] = True
    await update.message.reply_text(
        "Введите ник нового пользователя (без @):",
        reply_markup=ReplyKeyboardRemove()
    )


# ——— Общий хендлер текстовых сообщений ——————————————————

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    text = update.message.text or ""
    username = (update.effective_user.username or "").strip().lstrip("@").lower()

    # авто-активация любого pending
    user = await get_user_by_tg(tg_id)
    if not user:
        user = await activate_user(tg_id, username)
        if user:
            return await show_main_menu(update, role=user.role)
        return  # не приглашён — игнор

    if user.status is UserStatus.blocked:
        return  # игнор

    # ввод ника для «➕ Добавить пользователя»
    if context.user_data.pop("awaiting_new_username", False):
        uname = text.lstrip("@").lower()
        new = await invite_user(username=uname, role="User", invited_by=tg_id)
        return await update.message.reply_text(
            f"@{new.username} приглашён. Статус: ⏳",
            reply_markup=build_main_menu(user.role)
        )

    # меню-кнопки
    if text == "🧾 Меню бота":
        return await menu(update, context)
    if text == "📊 Статистика":
        return await stats_cmd(update, context)
    if text == "👥 Пользователи":
        return await users_list_cmd(update, context)
    if text == "➕ Добавить пользователя":
        return await start_add_user(update, context)

    # ссылки — только для active
    if user.status is not UserStatus.active:
        return

    urls = URL_PATTERN.findall(text)
    if not urls:
        await create_event(user_id=user.id, state="no link",
                           device_option_id=0, initial_url="", final_url="",
                           ip=None, isp=None)
        return await update.message.reply_text("❗ Пожалуйста, пришли одну ссылку.",
                                               reply_to_message_id=update.message.message_id)
    if len(urls) > 1:
        await create_event(user_id=user.id, state="many links",
                           device_option_id=0, initial_url="", final_url="",
                           ip=None, isp=None)
        return await update.message.reply_text("❗ Одну ссылку за раз, пожалуйста.",
                                               reply_to_message_id=update.message.message_id)

    raw_url = urls[0]
    try:
        device = await get_random_device()
    except ValueError as e:
        return await update.message.reply_text(str(e),
                                               reply_to_message_id=update.message.message_id)

    loop = asyncio.get_running_loop()
    try:
        initial_url, final_url, ip, isp, _, proxy_attempts = await loop.run_in_executor(
            None, partial(fetch_redirect, raw_url, device)
        )
    except ProxyAcquireError as e:
        for at in e.attempts:
            await create_proxy_log(at["attempt"], at["ip"], at["city"])
        await create_event(user_id=user.id, state="proxy error",
                           device_option_id=device["id"], initial_url=raw_url,
                           final_url="", ip=None, isp=None)
        return await update.message.reply_text(
            f"⚠️ Не удалось подобрать прокси за {len(e.attempts)} попыток.",
            reply_to_message_id=update.message.message_id
        )

    for at in proxy_attempts:
        await create_proxy_log(at["attempt"], at["ip"], at["city"])

    await create_event(user_id=user.id, state="success",
                       device_option_id=device["id"],
                       initial_url=initial_url, final_url=final_url,
                       ip=ip, isp=isp)

    report = (
        f"📱 Профиль: {device['model']}\n"
        f"   • UA: {device['ua']}\n"
        f"🔗 Начальный URL:\n{initial_url}\n"
        f"✅ Итоговый URL:\n{final_url}\n"
        f"🌐 IP: {ip}\n"
        f"📡 ISP: {isp}"
    )
    await update.message.reply_text(report,
                                    disable_web_page_preview=True,
                                    reply_to_message_id=update.message.message_id)


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(invite_detail_cb, pattern=r"^invite_\d+$"))
    app.add_handler(CallbackQueryHandler(revoke_cb,       pattern=r"^revoke_\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
