# bot/handlers.py

import re
import asyncio
from functools import partial
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler, Application

from db.crud import (
    invite_user,
    get_user_by_tg,
    activate_user,
    block_user_by_username,
    get_random_device,
    create_event,
    create_proxy_log,
)
from crawler.redirector import fetch_redirect, ProxyAcquireError
from config import INITIAL_ADMINS

URL_PATTERN = re.compile(r'https?://[^\s)]+')


# --- Утилита проверки доступа по ролям и статусу ---
async def check_access(update: Update, roles_allowed: list[str]) -> bool:
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status != "active" or user.role not in roles_allowed:
        await update.message.reply_text(
            "❌ Доступ запрещён.",
            reply_to_message_id=update.message.message_id
        )
        return False
    return True


# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    username_raw = update.effective_user.username or ""
    username = username_raw.strip().lstrip("@").lower()

    # Если уже есть активный юзер — просто привет
    user = await get_user_by_tg(tg_id)
    if user:
        if user.status == "active":
            return await update.message.reply_text(
                "Привет! Пришли мне ссылку, и я по ней перейду.",
                reply_to_message_id=update.message.message_id
            )
        if user.status == "blocked":
            # игнорируем заблокированных
            return

    # Пытаемся активировать pending-пользователя по нику
    activated = await activate_user(tg_id, username)
    if activated:
        return await update.message.reply_text(
            f"Привет, @{activated.username}! Ты активирован как {activated.role}. "
            "Пришли мне ссылку, и я по ней перейду.",
            reply_to_message_id=update.message.message_id
        )

    # Не найден ни в active, ни в pending → нет доступа
    await update.message.reply_text(
        "❌ У тебя нет доступа. Обратись к администратору.",
        reply_to_message_id=update.message.message_id
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

    username = context.args[0].lstrip("@").lower()
    new = await invite_user(username=username, role="User", invited_by=update.effective_user.id)
    await update.message.reply_text(
        f"Пользователь @{new.username} приглашён с ролью {new.role}. Статус: {new.status}.",
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

    username = context.args[0].lstrip("@").lower()
    new = await invite_user(username=username, role="Maintainer", invited_by=update.effective_user.id)
    await update.message.reply_text(
        f"Пользователь @{new.username} приглашён с ролью {new.role}. Статус: {new.status}.",
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

    username = context.args[0].lstrip("@").lower()
    new = await invite_user(username=username, role="Admin", invited_by=update.effective_user.id)
    await update.message.reply_text(
        f"Пользователь @{new.username} приглашён с ролью {new.role}. Статус: {new.status}.",
        reply_to_message_id=update.message.message_id
    )


# --- Команда /block (Admin & Maintainer) ---
async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, ["Admin", "Maintainer"]):
        return
    if len(context.args) != 1:
        return await update.message.reply_text(
            "Использование: /block <username>",
            reply_to_message_id=update.message.message_id
        )

    username = context.args[0].lstrip("@").lower()
    ok = await block_user_by_username(username)
    if ok:
        await update.message.reply_text(
            f"❌ @{username} заблокирован.",
            reply_to_message_id=update.message.message_id
        )
    else:
        await update.message.reply_text(
            f"⚠️ Пользователь @{username} не найден.",
            reply_to_message_id=update.message.message_id
        )


# --- Обработка любых текстовых сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    username_raw = update.effective_user.username or ""
    username = username_raw.strip().lstrip("@").lower()

    user = await get_user_by_tg(tg_id)
    if user and user.status == "blocked":
        return  # игнорируем

    if not user:
        # пытаемся активировать по нику
        user = await activate_user(tg_id, username)
        if user:
            return await update.message.reply_text(
                f"Привет, @{user.username}! Ты активирован как {user.role}. "
                "Пришли мне ссылку, и я по ней перейду.",
                reply_to_message_id=update.message.message_id
            )
        # не приглашён — игнорируем
        return

    # дальше — только active
    text = update.message.text or ""
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


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_user", add_user))
    app.add_handler(CommandHandler("add_mod", add_mod))
    app.add_handler(CommandHandler("add_admin", add_admin))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
