# main.py
import asyncio
from telegram.ext import ApplicationBuilder
from config import TELEGRAM_TOKEN
from db.database import init_db
from bot.handlers import register_handlers

def main():
    # 1) новый event loop                     ← изменено (строки 5–6)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 2) инициализация БД
    loop.run_until_complete(init_db())

    # 3) сборка и запуск бота
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)
    print("🤖 Бот запущен, ожидаю сообщений...")
    app.run_polling()                         # теперь синхронно

if __name__ == "__main__":
    main()
