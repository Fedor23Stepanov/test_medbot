# main.py

import asyncio
from telegram.ext import ApplicationBuilder
from config import TELEGRAM_TOKEN
from db.database import init_db
from db.seed import seed_initial_admins
from bot.handlers import register_handlers

def main():
    # создаём и устанавливаем собственный event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 1) инициализация БД (создание таблиц)
    loop.run_until_complete(init_db())

    # 2) сидирование начальных админов из конфига (pending → они будут активированы при /start)
    loop.run_until_complete(seed_initial_admins())

    # 3) сборка и запуск бота
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    print("🤖 Бот запущен, ожидаю сообщений...")
    app.run_polling()  # запускает собственный цикл
        

if __name__ == "__main__":
    main()
