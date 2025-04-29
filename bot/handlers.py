# bot/handlers.py

import asyncio
from functools import partial

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler, Application

from db.crud import (
    get_or_create_user,
    get_random_device,
    create_event,
    create_proxy_log
)
from crawler.redirector import fetch_redirect, ProxyAcquireError

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Отправь мне ссылку, и я покажу, куда она редиректит."
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_url = update.message.text.strip()

    # 1) Пользователь
    user = await get_or_create_user(
        tg_id=update.effective_user.id,
        username=update.effective_user.username or ""
    )

    # 2) Профиль устройства
    try:
        device = await get_random_device()
    except ValueError as e:
        return await update.message.reply_text(str(e))

    # 3) Сообщаем параметры
    msg = (
        f"🚀 Начинаю переход по {raw_url}\n\n"
        f"📱 Профиль #{device['id']}: {device['model']}\n"
        f"   • UA: {device['ua']}\n"
        f"   • Размер экрана: {device['css_size'][0]}×{device['css_size'][1]}\n"
        f"   • DPR: {device['dpr']}, mobile={device['mobile']}\n"
    )
    await update.message.reply_text(msg)

    # 4) Запускаем fetch_redirect в executor
    loop = asyncio.get_running_loop()
    try:
        initial_url, final_url, ip, isp, _, proxy_attempts = await loop.run_in_executor(
            None,
            partial(fetch_redirect, raw_url, device)
        )
    except ProxyAcquireError as e:
        for at in e.attempts:
            await create_proxy_log(
                attempt=at["attempt"],
                ip=at["ip"],
                city=at["city"]
            )
        return await update.message.reply_text(
            f"⚠️ Не удалось подобрать московский прокси за {len(e.attempts)} попыток."
        )

    # 5) Логируем прокси
    for at in proxy_attempts:
        await create_proxy_log(
            attempt=at["attempt"],
            ip=at["ip"],
            city=at["city"]
        )

    # 6) Сохраняем событие без status_code
    await create_event(
        user_id=user.id,
        device_option_id=device["id"],
        initial_url=initial_url,
        final_url=final_url,
        ip=ip,
        isp=isp
    )

    # 7) Отправляем результат
    await update.message.reply_text(
        f"🔗 Начальный URL: {initial_url}\n"
        f"✅ Итоговый URL: {final_url}\n"
        f"🌐 IP: {ip} (ISP: {isp})"
    )

def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.Regex(r"^https?://"), handle_link)
    )
