#populate_devices.py

import asyncio
from sqlalchemy import delete
from db.database import init_db, AsyncSessionLocal
from db.models import DeviceOption

# Здесь — ваши данные
DEVICE_DATA = {
    "1": {
        "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.105 Mobile Safari/537.36",
        "css_size": [412, 915],
        "platform": "Linux aarch64",
        "dpr": 3,
        "mobile": True,
        "model": "Google Pixel 8 Pro"
    },
    "2": {
        "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "css_size": [393, 852],
        "platform": "iPhone",
        "dpr": 3,
        "mobile": True,
        "model": "Apple iPhone 15 Pro"
    },
    "3": {
        "ua": "Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.111 Mobile Safari/537.36",
        "css_size": [360, 800],
        "platform": "Linux aarch64",
        "dpr": 3,
        "mobile": True,
        "model": "Samsung Galaxy S23"
    },
    "4": {
        "ua": "Mozilla/5.0 (Linux; Android 12; SM-A528B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.134 Mobile Safari/537.36",
        "css_size": [412, 915],
        "platform": "Linux aarch64",
        "dpr": 2.5,
        "mobile": True,
        "model": "Samsung Galaxy A52s 5G"
    },
    "5": {
        "ua": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.78 Mobile Safari/537.36",
        "css_size": [412, 915],
        "platform": "Linux aarch64",
        "dpr": 3,
        "mobile": True,
        "model": "Samsung Galaxy S24 Ultra"
    }
}

async def main():
    # 1) Создаём таблицы, если ещё не созданы
    await init_db()

    async with AsyncSessionLocal() as session:
        # (опционально) очищаем старые записи
        await session.execute(delete(DeviceOption))

        # 2) Добавляем каждую запись
        for id_str, opt in DEVICE_DATA.items():
            device = DeviceOption(
                id           = int(id_str),
                ua           = opt["ua"],
                css_size     = opt["css_size"],
                platform     = opt["platform"],
                # модель БД хранит dpr как Integer, поэтому приводим
                dpr          = int(opt["dpr"]),
                mobile       = 1 if opt["mobile"] else 0,
                model        = opt.get("model")
            )
            session.add(device)

        # 3) Фиксируем изменения
        await session.commit()

    print("✔️  Всё готово — данные записаны в таблицу device_options")

if __name__ == "__main__":
    asyncio.run(main())
