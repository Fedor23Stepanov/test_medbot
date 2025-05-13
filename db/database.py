# db/database.py

import os
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from .models import Base, User, UserStatus, UserRole  # предположительно есть перечисления ролей
from .crud import invite_user, get_user_by_username
from ..config import settings  # в settings.ADMIN_USERNAME и settings.DATABASE_URL

# Создаём движок
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=getattr(settings, "DB_ECHO", False),
    future=True,
)

# Фабрика сессий
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """
    Создаёт таблицы и добавляет initial admin (pending), если его ещё нет.
    Вызывать при старте приложения.
    """
    # 1) создаём все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2) проверяем, существует ли уже запись initial admin
    admin_nick = settings.ADMIN_USERNAME.strip().lstrip("@").lower()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.username == admin_nick)
        )
        admin = result.scalars().first()

        if not admin:
            # Создаём pending-пользователя с ролью admin
            # invited_by=None, т.к. это первый пользователь
            await invite_user(
                username=admin_nick,
                role=UserRole.ADMIN,       # или просто 'admin'
                invited_by=None            # или 0, если поле не nullable
            )
            print(f"[init_db] Initial admin @{admin_nick} created with status PENDING.")
        else:
            print(f"[init_db] Admin @{admin_nick} already exists (status={admin.status}).")
