# db/crud.py

import datetime
from sqlalchemy.future import select

from .database import AsyncSessionLocal
from .models import User, DeviceOption, Event, ProxyLog


# --- User ---

async def get_or_create_user(tg_id: int, username: str) -> User:
    """
    Возвращает существующего пользователя с данным tg_id,
    либо создаёт нового с переданным username.
    """
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


# --- DeviceOption ---

async def get_device_option(device_id: int) -> dict:
    """
    Возвращает словарь с параметрами эмуляции для устройства device_id:
      {
        "ua": str,
        "css_size": [width:int, height:int],
        "platform": str,
        "dpr": int,
        "mobile": bool,
        "model": str|None
      }
    """
    async with AsyncSessionLocal() as db:
        q = await db.execute(
            select(DeviceOption).where(DeviceOption.id == device_id)
        )
        opt = q.scalars().first()
        if not opt:
            raise ValueError(f"DeviceOption с id={device_id} не найден")
        return {
            "ua":       opt.ua,
            "css_size": opt.css_size,
            "platform": opt.platform,
            "dpr":      opt.dpr,
            "mobile":   bool(opt.mobile),
            "model":    opt.model,
        }


# --- ProxyLog ---

async def create_proxy_log(
    attempt: int,
    ip: str | None,
    city: str | None
) -> ProxyLog:
    """
    Создаёт запись в proxy_logs о попытке подобрать московский прокси.
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


# --- Event ---

async def create_event(
    user_id: int,
    device_option_id: int,
    initial_url: str,
    final_url: str,
    ip: str | None,
    isp: str | None
) -> Event:
    """
    Создаёт запись о событии редиректа и возвращает её.
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
