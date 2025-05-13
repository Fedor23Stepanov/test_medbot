# db/database.py

import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from .models import Base, User, UserStatus
from config import DATABASE_URL, ADMIN_USERNAME  # убедитесь, что в вашем config.py есть эти константы

# создаём подключение и фабрику сессий
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    Создаёт все таблицы и при первом запуске добавляет администратора
    (статус pending) из конфига. Если пользователь с таким username
    уже есть, повторно не добавляет.
    """
    # 1) создаём таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2) инициализируем initial admin
    admin_uname = ADMIN_USERNAME.strip().lstrip("@").lower()
    async with AsyncSessionLocal() as session:
        # проверяем, есть ли уже юзер с таким username
        result = await session.execute(
            select(User).where(User.username == admin_uname)
        )
        existing = result.scalars().first()

        if existing is None:
            new_admin = User(
                username=admin_uname,
                role="admin",
                status=UserStatus.pending,
                invited_by=None,
                created_at=datetime.datetime.utcnow(),
                # tg_id и activated_at останутся пустыми, 
                # заполнятся при первом сообщении от админа
            )
            session.add(new_admin)
            await session.commit()
