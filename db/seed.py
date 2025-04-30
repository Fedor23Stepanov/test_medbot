# db/seed.py

import datetime
from sqlalchemy.future import select

from config import INITIAL_ADMINS
from .database import AsyncSessionLocal
from .models import User, UserStatus

async def seed_initial_admins():
    """
    Добавляет в таблицу users записи для всех никнеймов из INITIAL_ADMINS
    со статусом 'pending' и ролью 'Admin', если их ещё нет.
    """
    async with AsyncSessionLocal() as db:
        for username in INITIAL_ADMINS:
            result = await db.execute(
                select(User).where(User.username == username)
            )
            existing = result.scalars().first()
            if not existing:
                user = User(
                    tg_id=None,
                    username=username,
                    role="Admin",
                    status=UserStatus.pending,
                    invited_by=None,
                    created_at=datetime.datetime.utcnow(),
                )
                db.add(user)
        await db.commit()
