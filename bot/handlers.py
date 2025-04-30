# bot/handlers.py
import re
import asyncio
from functools import partial
from telegram import Update
from telegram.ext import (
    ContextTypes, MessageHandler, filters, CommandHandler, Application
)
from db.crud import (
    get_or_create_user, get_random_device,
    create_event, create_proxy_log,
    get_user_role, set_user_role
)
from crawler.redirector import fetch_redirect, ProxyAcquireError

URL_PATTERN = re.compile(r'https?://[^\s)]+')

# --- Утилита проверки доступа по ролям ---
async def check_access(update: Update, roles_allowed: list[str]) -> bool:
    tg_id = update.effective_user.id
    role = await get_user_role(tg_id)
    if role not in roles_allowed:
        #await update.message.reply_text(
        #    "❌ Доступ запрещён.",
        #    reply_to_message_id=update.message.message_id
        #)
        return False
    return True

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1) Получаем или создаём запись в БД
    user = await get_or_create_user(
        tg_id=update.effective_user.id,
        username=update.effective_user.username or ""
    )
    # 2) Если это новый пользователь И его username в списке админов — даём роль Admin
    current_role = await get_user_role(user.tg_id)
    if current_role != "Admin" and (update.effective_user.username in INITIAL_ADMINS):
        await set_user_role(user.tg_id, "Admin")
    # 3) Приветственное сообщение    
    await update.message.reply_text(
        "Привет! Пришли мне ссылку и я по ней перейду."
    )

# --- Команда /add_user (Admin & Maintainer) ---
async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, ["Admin", "Maintainer"]):
        return
    if len(context.args) != 1:
        return await update.message.reply_text(
            "Использование: /add_user <username>",
            reply_to_message_id=update.message.message_id
        )
    username = context.args[0].lstrip("@")
    # Получаем или создаём запись (tg_id=0, т.к. юзер ещё не писал боту)
    user = await get_or_create_user(0, username)
    await set_user_role(user.tg_id, "User")
    await update.message.reply_text(
        f"Пользователь @{username} добавлен как User.",
        reply_to_message_id=update.message.message_id
    )

# --- Команда /add_mod (Admin only) ---
async def add_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, ["Admin"]):
        return
    if len(context.args) != 1:
        return await update.message.reply_text(
            "Использование: /add_mod <username>",
            reply_to_message_id=update.message.message_id
        )
    username = context.args[0].lstrip("@")
    user = await get_or_create_user(0, username)
    await set_user_role(user.tg_id, "Maintainer")
    await update.message.reply_text(
        f"Пользователь @{username} добавлен как Maintainer.",
        reply_to_message_id=update.message.message_id
    )

# --- Команда /add_admin (Admin only) ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, ["Admin"]):
        return
    if len(context.args) != 1:
        return await update.message.reply_text(
            "Использование: /add_admin <username>",
            reply_to_message_id=update.message.message_id
        )
    username = context.args[0].lstrip("@")
    user = await get_or_create_user(0, username)
    await set_user_role(user.tg_id, "Admin")
    await update.message.reply_text(
        f"Пользователь @{username} добавлен как Admin.",
        reply_to_message_id=update.message.message_id
    )

# --- Обработка любых текстовых сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # проверяем, что пользователь в нашей БД и имеет право работать с ботом
    if not await check_access(update, ["Admin", "Maintainer", "User"]):
        return

    # получаем или создаём запись User
    user = await get_or_create_user(
        tg_id=update.effective_user.id,
        username=update.effective_user.username or ""
    )

    text = update.message.text or ""
    urls = URL_PATTERN.findall(text)

    # 1) Нет ссылок
    if not urls:
        await create_event(
            user_id=user.id,
            state="no link",
            device_option_id=0,
            initial_url="",
            final_url="",
            ip=None,
            isp=None
        )
        return await update.message.reply_text(
            "❗ Пожалуйста, пришли одну ссылку.",
            reply_to_message_id=update.message.message_id
        )

    # 2) Слишком много ссылок
    if len(urls) > 1:
        await create_event(
            user_id=user.id,
            state="many links",
            device_option_id=0,
            initial_url="",
            final_url="",
            ip=None,
            isp=None
        )
        return await update.message.reply_text(
            "❗ Одну ссылку за раз, пожалуйста.",
            reply_to_message_id=update.message.message_id
        )

    raw_url = urls[0]

    # 3) Получаем случайное устройство
    try:
        device = await get_random_device()
    except ValueError as e:
        return await update.message.reply_text(
            str(e),
            reply_to_message_id=update.message.message_id
        )

    # 4) Запускаем редирект в потоках, ловим прокси-ошибку
    loop = asyncio.get_running_loop()
    try:
        initial_url, final_url, ip, isp, _, proxy_attempts = await loop.run_in_executor(
            None, partial(fetch_redirect, raw_url, device)
        )
    except ProxyAcquireError as e:
        # лог каждой попытки
        for at in e.attempts:
            await create_proxy_log(at["attempt"], at["ip"], at["city"])
        # сохраняем событие
        await create_event(
            user_id=user.id,
            state="proxy error",
            device_option_id=device["id"],
            initial_url=raw_url,
            final_url="",
            ip=None,
            isp=None
        )
        return await update.message.reply_text(
            f"⚠️ Не удалось подобрать прокси за {len(e.attempts)} попыток.",
            reply_to_message_id=update.message.message_id
        )

    # 5) Логируем все успешные попытки прокси подбора
    for at in proxy_attempts:
        await create_proxy_log(at["attempt"], at["ip"], at["city"])

    # 6) Сохраняем успешное событие
    await create_event(
        user_id=user.id,
        state="success",
        device_option_id=device["id"],
        initial_url=initial_url,
        final_url=final_url,
        ip=ip,
        isp=isp
    )

    # 7) Формируем отчёт (с исправленным переносом строки)
    report = (
        f"📱 Профиль: {device['model']}\n"
        f"   • UA: {device['ua']}\n"
        f"🔗 Начальный URL:\n{initial_url}\n"
        f"✅ Итоговый URL:\n{final_url}\n"
        f"🌐 IP: {ip}\n"
        f"📡 ISP: {isp}"
    )

    # 8) Один ответ-цитата без предпросмотра
    await update.message.reply_text(
        report,
        disable_web_page_preview=True,
        reply_to_message_id=update.message.message_id
    )

def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_user", add_user))
    app.add_handler(CommandHandler("add_mod", add_mod))
    app.add_handler(CommandHandler("add_admin", add_admin))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
