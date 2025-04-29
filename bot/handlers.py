# bot/handlers.py
import asyncio
from functools import partial

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler, Application

from db.crud import get_or_create_user, get_random_device, create_event, create_proxy_log
from crawler.redirector import fetch_redirect, ProxyAcquireError

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — приветствие."""
    await update.message.reply_text(
        "Привет! Отправь мне ссылку, и я покажу, куда она редиректит."
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Пользователь прислал URL:
      1) Берём или создаём профиль пользователя
      2) Достаём случайное устройство из БД
      3) Сообщаем параметры устройства в чат
      4) Запускаем fetch_redirect в executor
      5) Логируем попытки прокси и сохраняем событие
      6) Отправляем пользователю результаты
    """
    raw_url = update.message.text.strip()

    # 1) Получаем или создаём запись о пользователе
    user = await get_or_create_user(
        tg_id=update.effective_user.id,
        username=update.effective_user.username or ""
    )

    # 2) Случайный профиль устройства
    try:
        device = await get_random_device()
    except ValueError as e:
        return await update.message.reply_text(str(e))

    # 3) Уведомляем пользователя, какой профиль выбрали
    msg = (
        f"🚀 Начинаю переход по {raw_url}\n\n"
        f"📱 Выбран профиль #{device['id']}: {device['model']}\n"
        f"   • UA: {device['ua']}\n"
        f"   • Размер экрана: {device['css_size'][0]}×{device['css_size'][1]}\n"
        f"   • DPR: {device['dpr']}, mobile={device['mobile']}\n"
    )
    await update.message.reply_text(msg)

    # 4) Запускаем sync-код в отдельном потоке
    loop = asyncio.get_running_loop()
    try:
        initial_url, final_url, ip, isp, _, proxy_attempts = await loop.run_in_executor(
            None,
            partial(fetch_redirect, raw_url, device)
        )
    except ProxyAcquireError as e:
        # 5a) Не удалось получить московский прокси
        for at in e.attempts:
            await create_proxy_log(
                attempt=at["attempt"],
                ip=at["ip"],
                city=at["city"]
            )
        return await update.message.reply_text(
            f"⚠️ Не удалось подобрать московский прокси "
            f"за {len(e.attempts)} попыток."
        )

    # 5b) Логируем все успешные попытки в БД
    for at in proxy_attempts:
        await create_proxy_log(
            attempt=at["attempt"],
            ip=at["ip"],
            city=at["city"]
        )

    # Сохраняем сам факт перехода
    await create_event(
        user_id=user.id,
        device_option_id=device["id"],
        initial_url=initial_url,
        final_url=final_url,
        status_code=0,  # или прокинуть реальный HTTP статус, если есть
        ip=ip,
        isp=isp
    )

    # 6) Отправляем результат пользователю
    await update.message.reply_text(
        f"🔗 Начальный URL: {initial_url}\n"
        f"✅ Итоговый URL: {final_url}\n"
        f"🌐 IP: {ip} (ISP: {isp})"
    )

def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    # Любое сообщение, начинающееся с http:// или https://
    app.add_handler(
        MessageHandler(filters.Regex(r"^https?://"), handle_link)
    )
