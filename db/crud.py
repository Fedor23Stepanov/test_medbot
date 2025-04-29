# db/crud.py

import datetime
from sqlalchemy.future import select
from sqlalchemy import func
from .database import AsyncSessionLocal
from .models import User, DeviceOption, ProxyLog, Event

async def get_or_create_user(tg_id: int, username: str) -> User:
    """
    Возвращает существующего пользователя с данным tg_id,
    либо создаёт нового с переданным username.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalars().first()
        if user:
            return user

        user = User(
            tg_id=tg_id,
            username=username,
            created_at=datetime.datetime.utcnow()
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

async def get_random_device() -> dict:
    """
    Возвращает один случайный профиль устройства из БД в виде dict:
    {
        "id": int,
        "ua": str,
        "css_size": [width:int, height:int],
        "platform": str,
        "dpr": int,
        "mobile": bool,
        "model": str|None
    }
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DeviceOption)
            .order_by(func.random())
            .limit(1)
        )
        dev = result.scalars().first()
        if not dev:
            raise ValueError("В базе нет ни одного профиля устройства")
        return {
            "id": dev.id,
            "ua": dev.ua,
            "css_size": dev.css_size,
            "platform": dev.platform,
            "dpr": dev.dpr,
            "mobile": bool(dev.mobile),
            "model": dev.model,
        }

async def create_proxy_log(
    attempt: int,
    ip: str | None,
    city: str | None
) -> ProxyLog:
    """
    Создаёт запись о попытке подобрать московский прокси.
    """
    async with AsyncSessionLocal() as db:
        log = ProxyLog(
            attempt=attempt,
            ip=ip,
            city=city,
            timestamp=datetime.datetime.utcnow()
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return log

async def create_event(
    user_id: int,
    device_option_id: int,
    initial_url: str,
    final_url: str,
    ip: str | None,
    isp: str | None
) -> Event:
    """
    Создаёт запись о событии редиректа.
    """
    async with AsyncSessionLocal() as db:
        ev = Event(
            user_id=user_id,
            device_option_id=device_option_id,
            initial_url=initial_url,
            final_url=final_url,
            ip=ip,
            isp=isp,
            timestamp=datetime.datetime.utcnow()
        )
        db.add(ev)
        await db.commit()
        await db.refresh(ev)
        return ev
