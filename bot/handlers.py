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
    activate_user,
    invite_user,
    list_pending_users,
    revoke_invitation,
    get_user_stats,
    block_user_by_username,
    get_random_device,
    create_event,
    create_proxy_log,
)
from crawler.redirector import fetch_redirect, ProxyAcquireError
from db.models import UserStatus

URL_PATTERN = re.compile(r'https?://[^\s)]+')


# ——— Помощники по меню —————————————————————————————

def build_main_menu(role: str) -> ReplyKeyboardMarkup:
    """
    Основное меню: все видят Статистика и Настройки,
    а модеры и админы — ещё Пользователи и Добавить пользователя.
    """
    keyboard = [
        ["📊 Статистика", "⚙️ Настройки"]
    ]
    if role in ("Maintainer", "Admin"):
        keyboard.append(["👥 Пользователи", "➕ Добавить пользователя"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def show_main_menu(update: Update, role: str):
    """Отправить или обновить главное меню пользователя."""
    await update.message.reply_text(
        "🧾 Меню бота",
        reply_markup=build_main_menu(role)
    )


# ——— /start и /menu ————————————————————————————————

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    username = (update.effective_user.username or "").strip().lstrip("@").lower()

    # если уже есть активный — просто меню
    user = await get_user_by_tg(tg_id)
    if user and user.status is UserStatus.active:
        return await show_main_menu(update, role=user.role)
    if user and user.status is UserStatus.blocked:
        return  # игнорируем заблокированных

    # иначе пробуем активировать pending-пользователя
    activated = await activate_user(tg_id, username)
    if activated:
        return await show_main_menu(update, role=activated.role)

    # никто не нашёлся — отказ
    await update.message.reply_text(
        "❌ У тебя нет доступа. Обратись к администратору.",
        reply_markup=ReplyKeyboardRemove()
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /menu — показать главное меню (если активен)."""
    user = await get_user_by_tg(update.effective_user.id)
    if user and user.status is UserStatus.active:
        await show_main_menu(update, role=user.role)


# ——— Статистика ——————————————————————————————————

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 📊 Статистика."""
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active:
        return
    stats = await get_user_stats(user.id)
    text = (
        f"📊 Твоя статистика:\n"
        f"• За всё время: {stats['all_time']}\n"
        f"• За последний месяц: {stats['last_month']}\n"
        f"• За последнюю неделю: {stats['last_week']}"
    )
    await update.message.reply_text(
        text,
        reply_markup=build_main_menu(user.role)
    )


# ——— Список приглашённых пользователей —————————————————

async def users_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Кнопка 👥 Пользователи:
    – модеры видят только своих pending-приглашённых,
    – админ видит всех pending-приглашённых.
    """
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active:
        return
    if user.role not in ("Maintainer", "Admin"):
        return

    # получаем тех, кого нужно показать
    if user.role == "Admin":
        pendings = await list_pending_users()
    else:  # Maintainer
        pendings = await list_pending_users(invited_by=user.tg_id)

    if not pendings:
        await update.message.reply_text(
            "Нет активных приглашений.",
            reply_markup=build_main_menu(user.role)
        )
        return

    # строим инлайн-кнопки: username + эмодзи статуса
    buttons = []
    for u in pendings:
        emoji = {
            UserStatus.pending:  "⏳",
            UserStatus.active:   "✅",
            UserStatus.blocked:  "⛔️"
        }.get(u.status, "")
        text = f"@{u.username} {emoji}"
        buttons.append([InlineKeyboardButton(text, callback_data=f"invite_{u.id}")])

    await update.message.reply_text(
        "👥 Приглашённые пользователи:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def invite_detail_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Колбэк при нажатии на одного из приглашённых."""
    q = update.callback_query
    await q.answer()
    _, uid = q.data.split("_", 1)
    user = await get_user_by_tg(int(uid))  # или fetch по id, если добавите функцию get_user_by_id
    if not user:
        return await q.edit_message_text("Пользователь не найден.")

    emoji = {
        UserStatus.pending:  "⏳ Ожидает",
        UserStatus.active:   "✅ Активирован",
        UserStatus.blocked:  "⛔️ Заблокирован"
    }.get(user.status, "")
    text = f"@{user.username}\nСтатус: {emoji}"
    kb = [[InlineKeyboardButton("🗑️ Отозвать приглашение", callback_data=f"revoke_{user.id}")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def revoke_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Колбэк Отозвать приглашение."""
    q = update.callback_query
    await q.answer()
    _, uid = q.data.split("_", 1)
    success = await revoke_invitation(int(uid))
    if success:
        await q.edit_message_text("Приглашение отозвано.")
    else:
        await q.edit_message_text("Не удалось отозвать приглашение.")


# ——— Режим добавления через меню ——————————————————————

async def start_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка ➕ Добавить пользователя — переключаемся в режим ввода ника."""
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status is not UserStatus.active:
        return
    if user.role not in ("Maintainer", "Admin"):
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

    # 0) авто-активация pending при любом сообщении
    user = await get_user_by_tg(tg_id)
    if not user:
        user = await activate_user(tg_id, username)
        if user:
            return await show_main_menu(update, role=user.role)
        return  # не приглашён — игнорируем

    if user.status is UserStatus.blocked:
        return  # заблокирован — игнорируем

    # 1) режим ввода ника для добавления
    if context.user_data.get("awaiting_new_username"):
        uname = text.lstrip("@").lower()
        new = await invite_user(username=uname, role="User", invited_by=tg_id)
        context.user_data.pop("awaiting_new_username", None)
        return await update.message.reply_text(
            f"@{new.username} приглашён. Статус: ⏳",
            reply_markup=build_main_menu(user.role)
        )

    # 2) кнопки меню
    if text == "🧾 Меню Бота":
        return await menu(update, context)
    if text == "📊 Статистика":
        return await stats_cmd(update, context)
    if text == "👥 Пользователи":
        return await users_list_cmd(update, context)
    if text == "➕ Добавить пользователя":
        return await start_add_user(update, context)

    # 3) обработка ссылок (только для active)
    if user.status is not UserStatus.active:
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
    await update.message.reply_text(
        report,
        disable_web_page_preview=True,
        reply_to_message_id=update.message.message_id
    )


# ——— Регистрация хендлеров ————————————————————————

def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(invite_detail_cb, pattern=r"^invite_\d+$"))
    app.add_handler(CallbackQueryHandler(revoke_cb,       pattern=r"^revoke_\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
