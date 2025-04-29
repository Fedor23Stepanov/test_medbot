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
    create_event, create_proxy_log
)
from crawler.redirector import fetch_redirect, ProxyAcquireError

URL_PATTERN = re.compile(r'https?://[^\s)]+')  # добавлено

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Пришли мне любую ссылку — и я покажу, куда она редиректит."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    urls = URL_PATTERN.findall(text)

    # 0) валидация ссылок:
    if not urls:
        return await update.message.reply_text("❗ Пожалуйста, пришли ссылку.")
    if len(urls) > 1:
        return await update.message.reply_text("❗ Одну ссылку за раз, пожалуйста.")

    raw_url = urls[0]

    user = await get_or_create_user(
        tg_id=update.effective_user.id,
        username=update.effective_user.username or ""
    )
    try:
        device = await get_random_device()
    except ValueError as e:
        return await update.message.reply_text(str(e))

    loop = asyncio.get_running_loop()
    try:
        initial_url, final_url, ip, isp, _, proxy_attempts = await loop.run_in_executor(
            None, partial(fetch_redirect, raw_url, device)
        )
    except ProxyAcquireError as e:
        for at in e.attempts:
            await create_proxy_log(at["attempt"], at["ip"], at["city"])
        return await update.message.reply_text(
            f"⚠️ Не удалось подобрать прокси за {len(e.attempts)} попыток.",
            reply_to_message_id=update.message.message_id  # добавлено
        )

    for at in proxy_attempts:
        await create_proxy_log(at["attempt"], at["ip"], at["city"])

    await create_event(
        user_id=user.id,
        device_option_id=device["id"],
        initial_url=initial_url,
        final_url=final_url,
        ip=ip,
        isp=isp
    )

    report = (
        f"🚀 Переход по {raw_url}\n\n"
        f"📱 Профиль #{device['id']}: {device['model']}\n"
        f"   • UA: {device['ua']}\n"
        f"   • Экран: {device['css_size'][0]}×{device['css_size'][1]}\n"
        f"   • DPR={device['dpr']}, mobile={device['mobile']}\n\n"
        f"🔗 Начальный URL: {initial_url}\n"
        f"✅ Итоговый URL: {final_url}\n"
        f"🌐 IP: {ip} (ISP: {isp})"
    )

    # один итоговый reply с отключённым предпросмотром и reply_to_message_id
    await update.message.reply_text(
        report,
        disable_web_page_preview=True,            # добавлено
        reply_to_message_id=update.message.message_id  # добавлено
    )

def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
