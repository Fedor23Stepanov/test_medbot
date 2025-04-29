import asyncio
from telegram.ext import ApplicationBuilder
from config import TELEGRAM_TOKEN
from db.database import init_db
from bot.handlers import register_handlers

def main():
    # 0) Создаём и регистрируем наш event loop для polling
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 1) Инициализируем БД (внутри этого же loop)
    loop.run_until_complete(init_db())

    # 2) Строим и настраиваем Telegram-приложение
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)
    print("🤖 Бот запущен, ожидаю сообщений...")

    # 3) Запускаем блокирующее long-polling
    app.run_polling()

if __name__ == "__main__":
    main()
