# main.py

import asyncio

from telegram.ext import ApplicationBuilder

from config import TELEGRAM_TOKEN
from db.database import init_db
from bot.handlers import register_handlers

async def main():
    # 1) Инициализируем базу данных (создаст все таблицы)
    await init_db()

    # 2) Строим и настраиваем Telegram-приложение
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    print("🤖 Бот запущен, ожидаю сообщений...")

    # 3) Запускаем long-polling (блокирующий)
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
