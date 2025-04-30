# db/crud.py

import datetime
from typing import Optional, List

from sqlalchemy.future import select
from sqlalchemy import update, func
from .database import AsyncSessionLocal
from .models import (
    User, UserStatus,
    Event,
    DeviceOption, ProxyLog
)


# --- Работа с пользователями ---

async def invite_user(username: str, role: str, invited_by: Optional[int]) -> User:
    """
    Пригласить нового пользователя:
    создаёт запись с username, role и status='pending'.
    """
    async with AsyncSessionLocal() as db:
        user = User(
            tg_id=None,
            username=username,
            role=role,
            status=UserStatus.pending,
            invited_by=invited_by,
            created_at=datetime.datetime.utcnow()
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def activate_user(tg_id: int, username: str) -> Optional[User]:
    """
    При первом сообщении от pending-пользователя:
    ищем запись User(username, status='pending'),
    заполняем tg_id, переводим в active и ставим activated_at.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(
                User.username == username,
                User.status == UserStatus.pending
            )
        )
        user = result.scalars().first()
        if not user:
            return None

        user.tg_id = tg_id
        user.status = UserStatus.active
        user.activated_at = datetime.datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        return user


async def get_user_by_tg(tg_id: int) -> Optional[User]:
    """
    Возвращает User по telegram_id, либо None.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.tg_id == tg_id)
        )
        return result.scalars().first()


async def block_user_by_username(username: str) -> bool:
    """
    Ставит статус 'blocked' у пользователя с данным username.
    Возвращает True, если был обновлён хотя бы один ряд.
    """
    async with AsyncSessionLocal() as db:
        stmt = (
            update(User)
            .where(User.username == username)
            .values(status=UserStatus.blocked)
        )
        res = await db.execute(stmt)
        await db.commit()
        return bool(res.rowcount)

async def get_user_stats(user_id: int) -> dict:
    """
    Возвращает число успешных редиректов:
      – за всё время
      – за последний месяц
      – за последнюю неделю
    """
    async with AsyncSessionLocal() as db:
        now = datetime.datetime.utcnow()
        month_ago = now - datetime.timedelta(days=30)
        week_ago  = now - datetime.timedelta(days=7)

        total = (await db.execute(
            select(func.count()).select_from(Event)
            .where(Event.user_id == user_id, Event.state == "success")
        )).scalar_one()

        last_month = (await db.execute(
            select(func.count()).select_from(Event)
            .where(
                Event.user_id == user_id,
                Event.state == "success",
                Event.timestamp >= month_ago
            )
        )).scalar_one()

        last_week = (await db.execute(
            select(func.count()).select_from(Event)
            .where(
                Event.user_id == user_id,
                Event.state == "success",
                Event.timestamp >= week_ago
            )
        )).scalar_one()

        return {
            "all_time":   total,
            "last_month": last_month,
            "last_week":  last_week,
        }


async def list_active_users() -> List[User]:
    """
    Возвращает всех пользователей со статусом active
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.status == UserStatus.active)
        )
        return result.scalars().all()


async def get_user_by_id(user_id: int) -> Optional[User]:
    """
    Возвращает User по его internal ID
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalars().first()

# --- Исправленный импорт позволяет корректно выбирать случайное устройство ---

async def get_random_device() -> dict:
    """
    Возвращает случайный профиль устройства из БД.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DeviceOption)
            .order_by(func.random())    # теперь func определён
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
    ip: Optional[str],
    city: Optional[str]
) -> ProxyLog:
    """
    Логирует попытку подобрать прокси.
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
    state: str,
    device_option_id: int,
    initial_url: str,
    final_url: str,
    ip: Optional[str],
    isp: Optional[str]
) -> Event:
    """
    Логирует результат обхода ссылки.
    """
    async with AsyncSessionLocal() as db:
        ev = Event(
            user_id=user_id,
            state=state,
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
