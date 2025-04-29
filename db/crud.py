# db/crud.py

import datetime
from sqlalchemy.future import select
from sqlalchemy import func, delete
from .database import AsyncSessionLocal
from .models import User, DeviceOption, Event, ProxyLog

# --- User ---
async def get_or_create_user(tg_id: int, username: str) -> User:
    async with AsyncSessionLocal() as db:
        q = await db.execute(select(User).where(User.tg_id == tg_id))
        user = q.scalars().first()
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

# --- Random Device ---
async def get_random_device() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DeviceOption).order_by(func.random()).limit(1)
        )
        device = result.scalars().first()
        if not device:
            raise ValueError("В базе нет ни одного профиля устройства")
        return {
            "id": device.id,
            "ua": device.ua,
            "css_size": device.css_size,
            "platform": device.platform,
            "dpr": device.dpr,
            "mobile": bool(device.mobile),
            "model": device.model,
        }

# --- ProxyLog ---
async def create_proxy_log(
    attempt: int,
    ip: str | None,
    city: str | None
) -> ProxyLog:
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

# --- Event ---
async def create_event(
    user_id: int,
    device_option_id: int,
    initial_url: str,
    final_url: str,
    ip: str | None,
    isp: str | None
) -> Event:
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
