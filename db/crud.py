# db/crud.py

import datetime
from typing import Optional, List

from sqlalchemy.future import select
from sqlalchemy import update, func, delete
from .database import AsyncSessionLocal
from .models import (
    User, UserStatus, TransitionMode, NotificationMode,
    Event, DeviceOption, ProxyLog
)


# --- Пользователи ---

async def get_user_by_username(username: str) -> Optional[User]:
    """
    Возвращает User по username, либо None.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.username == username)
        )
        return result.scalars().first()


async def get_user_by_tg(tg_id: int) -> Optional[User]:
    """
    Возвращает User по telegram_id, либо None.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.tg_id == tg_id)
        )
        return result.scalars().first()


async def get_user_by_id(user_id: int) -> Optional[User]:
    """
    Возвращает User по его internal ID.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalars().first()


async def list_pending_users(invited_by: int | None = None) -> List[User]:
    """
    Возвращает список pending-пользователей.
    Если invited_by указан, только тех, кого пригласил invited_by.
    """
    async with AsyncSessionLocal() as db:
        q = select(User).where(User.status == UserStatus.pending)
        if invited_by is not None:
            q = q.where(User.invited_by == invited_by)
        result = await db.execute(q)
        return result.scalars().all()


async def list_active_users() -> List[User]:
    """
    Возвращает всех активных пользователей.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.status == UserStatus.active)
        )
        return result.scalars().all()


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
    ищем запись (username, pending), заполняем tg_id, переводим в active и ставим activated_at.
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


async def revoke_invitation(user_id: int) -> bool:
    """
    Удаляет pending-приглашение по internal ID.
    """
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            delete(User).where(
                User.id == user_id,
                User.status == UserStatus.pending
            )
        )
        await db.commit()
        return bool(res.rowcount)


async def block_user(user_id: int) -> bool:
    """
    Блокирует пользователя (status → blocked).
    """
    async with AsyncSessionLocal() as db:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(status=UserStatus.blocked)
        )
        res = await db.execute(stmt)
        await db.commit()
        return bool(res.rowcount)


# --- Пользовательские настройки ---

async def set_transition_mode(user_id: int, mode: TransitionMode) -> bool:
    """
    Устанавливает режим перехода для пользователя.
    """
    async with AsyncSessionLocal() as db:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(transition_mode=mode)
        )
        res = await db.execute(stmt)
        await db.commit()
        return bool(res.rowcount)


async def set_notification_mode(user_id: int, mode: NotificationMode) -> bool:
    """
    Устанавливает режим уведомлений для пользователя.
    """
    async with AsyncSessionLocal() as db:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(notification_mode=mode)
        )
        res = await db.execute(stmt)
        await db.commit()
        return bool(res.rowcount)


# --- События и статистика ---

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
        week_ago = now - datetime.timedelta(days=7)

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
            "all_time": total,
            "last_month": last_month,
            "last_week": last_week,
        }


async def get_user_events(user_id: int) -> List[Event]:
    """
    Возвращает события пользователя, отсортированные по timestamp DESC.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Event)
            .where(Event.user_id == user_id)
            .order_by(Event.timestamp.desc())
        )
        return result.scalars().all()


# --- Устройства и прокси ---

async def get_random_device() -> dict:
    """
    Возвращает случайный профиль устройства из БД.
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
