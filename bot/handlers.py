# bot/handlers.py

import asyncio
from functools import partial

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    Application,
)

from db.crud import (
    get_or_create_user,
    get_device_option,
    create_event,
    create_proxy_log,
)
from crawler.redirector import fetch_redirect, ProxyAcquireError


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — приветствие."""
    await update.message.reply_text(
        "Привет! Отправь мне ссылку, и я покажу, куда она редиректит."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Первый этап: пользователь присылает URL.
    Сохраняем его в user_data и предлагаем выбрать профиль устройства.
    """
    url = update.message.text.strip()
    context.user_data["pending_url"] = url

    # Предлагаем клавиатуру с опциями (1, 2, 3)
    keyboard = [["1", "2", "3"]]
    await update.message.reply_text(
        "Выберите профиль устройства (отправьте цифру):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        ),
    )


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Второй этап: пользователь отправляет цифру профиля.
    Запускаем fetch_redirect в пуле, логируем попытки,
    сохраняем событие и отвечаем итогами.
    """
    choice = update.message.text.strip()
    if choice not in {"1", "2", "3"}:
        return await update.message.reply_text(
            "Неверный выбор. Пожалуйста, отправьте цифру 1, 2 или 3."
        )

    # Убедимся, что URL был передан
    raw_url = context.user_data.pop("pending_url", None)
    if not raw_url:
        return await update.message.reply_text(
            "Ссылка не найдена. Сначала отправьте URL."
        )

    device_option_id = int(choice)

    # Получаем или создаём пользователя
    user = await get_or_create_user(
        tg_id=update.effective_user.id,
        username=update.effective_user.username or ""
    )

    # Достаём параметры устройства из БД
    try:
        device_params = await get_device_option(device_option_id)
    except ValueError as e:
        return await update.message.reply_text(str(e))

    # Запускаем медленный sync-код в executor, чтобы не блокировать loop
    loop = asyncio.get_running_loop()
    try:
        initial_url, final_url, ip, isp, device, proxy_attempts = await loop.run_in_executor(
            None,
            partial(fetch_redirect, raw_url, device_params)
        )
    except ProxyAcquireError as e:
        # Если не удалось найти московский прокси — логируем все попытки
        for attempt in e.attempts:
            await create_proxy_log(
                attempt=attempt["attempt"],
                ip=attempt["ip"],
                city=attempt["city"]
            )
        return await update.message.reply_text(
            f"⚠️ Не удалось подобрать московский прокси "
            f"за {len(e.attempts)} попыток."
        )

    # Логируем каждую попытку в БД
    for attempt in proxy_attempts:
        await create_proxy_log(
            attempt=attempt["attempt"],
            ip=attempt["ip"],
            city=attempt["city"]
        )

    # Сохраняем событие редиректа
    # статус код пока неизвестен — можно передавать 0
    await create_event(
        user_id=user.id,
        device_option_id=device_option_id,
        initial_url=initial_url,
        final_url=final_url,
        status_code=0,
        ip=ip,
        isp=isp
    )

    # Отвечаем пользователю и убираем клавиатуру
    await update.message.reply_text(
        f"Начальный URL: {initial_url}\n"
        f"Итоговый URL: {final_url}\n"
        f"IP: {ip} (ISP: {isp})",
        reply_markup=ReplyKeyboardRemove()
    )


def register_handlers(app: Application):
    """
    Регистрирует все хэндлеры в переданном Application.
    """
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.Regex(r"^https?://"), handle_link)
    )
    app.add_handler(
        MessageHandler(filters.Regex(r"^[123]$"), handle_choice)
    )
