from telegram.ext import ApplicationBuilder
from config import TELEGRAM_TOKEN
from db.database import init_db
from bot.handlers import register_handlers

def main():
    # 1) Инициализируем БД (через asyncio)
    import asyncio
    asyncio.run(init_db())

    # 2) Строим и настраиваем Telegram-приложение
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)
    print("🤖 Бот запущен, ожидаю сообщений...")

    # 3) Запускаем long-polling (синхронно)
    app.run_polling()

if __name__ == "__main__":
    main()
