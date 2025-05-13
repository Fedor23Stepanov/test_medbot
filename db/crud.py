# db/crud.py

import datetime
from sqlalchemy.future import select
from sqlalchemy import func
from .database import AsyncSessionLocal
from .models import User, DeviceOption, ProxyLog, Event, UserStatus


async def get_user_by_tg(tg_id: int) -> User | None:
    """Найти пользователя по его Telegram ID."""
    async with AsyncSessionLocal() as db:
        q = await db.execute(
            select(User).where(User.tg_id == tg_id)
        )
        return q.scalars().first()


async def get_user_by_id(user_id: int) -> User | None:
    """Найти пользователя по внутреннему ID."""
    async with AsyncSessionLocal() as db:
        q = await db.execute(
            select(User).where(User.id == user_id)
        )
        return q.scalars().first()


async def activate_user(tg_id: int, username: str) -> User | None:
    """
    Активировать pending-пользователя по username (initial admin или приглашённый).
    Заполнить tg_id, пометить статус active и дату активации.
    """
    uname = username.strip().lstrip("@").lower()
    async with AsyncSessionLocal() as db:
        q = await db.execute(
            select(User)
            .where(User.username == uname, User.status == UserStatus.pending)
        )
        user = q.scalars().first()
        if not user:
            return None

        user.tg_id = tg_id
        user.status = UserStatus.active
        user.activated_at = datetime.datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        return user


async def invite_user(username: str, role: str, invited_by: int) -> User:
    """
    Создать нового pending-пользователя с указанной ролью и пригласителем.
    """
    uname = username.strip().lstrip("@").lower()
    async with AsyncSessionLocal() as db:
        user = User(
            username=uname,
            role=role,
            status=UserStatus.pending,
            invited_by=invited_by,
            created_at=datetime.datetime.utcnow(),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def list_pending_users(invited_by: int | None = None) -> list[User]:
    """
    Получить список всех pending-пользователей.
    Если invited_by указан, вернуть только те, кого пригласил этот tg_id.
    """
    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.status == UserStatus.pending)
        if invited_by is not None:
            stmt = stmt.where(User.invited_by == invited_by)
        result = await db.execute(stmt)
        return result.scalars().all()


async def revoke_invitation(user_id: int) -> bool:
    """
    Отозвать приглашение: удалить pending-пользователя по его ID.
    Возвращает True, если удалилось, иначе False.
    """
    async with AsyncSessionLocal() as db:
        q = await db.execute(
            select(User)
            .where(User.id == user_id, User.status == UserStatus.pending)
        )
        user = q.scalars().first()
        if not user:
            return False
        await db.delete(user)
        await db.commit()
        return True


async def get_user_stats(user_id: int) -> dict[str, int]:
    """
    Посчитать количество Event для пользователя:
    • all_time: всего
    • last_month: за последние 30 дней
    • last_week: за последние 7 дней
    """
    now = datetime.datetime.utcnow()
    async with AsyncSessionLocal() as db:
        # Всего
        total = (await db.execute(
            select(func.count())
            .select_from(Event)
            .where(Event.user_id == user_id)
        )).scalar_one()

        # Последний месяц
        m30 = now - datetime.timedelta(days=30)
        last_month = (await db.execute(
            select(func.count())
            .select_from(Event)
            .where(Event.user_id == user_id, Event.timestamp >= m30)
        )).scalar_one()

        # Последняя неделя
        w7 = now - datetime.timedelta(days=7)
        last_week = (await db.execute(
            select(func.count())
            .select_from(Event)
            .where(Event.user_id == user_id, Event.timestamp >= w7)
        )).scalar_one()

    return {
        "all_time": total,
        "last_month": last_month,
        "last_week": last_week,
    }


async def get_random_device() -> dict:
    """
    Случайный профиль устройства из БД.
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


async def create_proxy_log(attempt: int, ip: str | None, city: str | None) -> ProxyLog:
    """
    Логирование попытки подбора прокси.
    """
    async with AsyncSessionLocal() as db:
        log = ProxyLog(
            attempt=attempt,
            ip=ip,
            city=city,
            timestamp=datetime.datetime.utcnow(),
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
    ip: str | None,
    isp: str | None
) -> Event:
    """
    Запись события перехода по ссылке.
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
            timestamp=datetime.datetime.utcnow(),
        )
        db.add(ev)
        await db.commit()
        await db.refresh(ev)
        return ev
