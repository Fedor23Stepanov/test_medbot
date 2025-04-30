# db/crud.py

from sqlalchemy.future import select
from sqlalchemy import delete
from .models import User, UserStatus
from .database import AsyncSessionLocal

async def list_pending_users(invited_by: int | None = None) -> list[User]:
    """
    Возвращает список записей со статусом pending.
    Если invited_by задан — фильтруем по тому, кто их пригласил.
    """
    async with AsyncSessionLocal() as db:
        q = select(User).where(User.status == UserStatus.pending)
        if invited_by is not None:
            q = q.where(User.invited_by == invited_by)
        result = await db.execute(q)
        return result.scalars().all()

async def revoke_invitation(user_id: int) -> bool:
    """
    Удаляет из таблицы запись пользователя по internal id.
    Возвращает True, если запись была удалена.
    """
    async with AsyncSessionLocal() as db:
        res = await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
        return bool(res.rowcount)
