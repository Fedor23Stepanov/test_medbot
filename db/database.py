# db/database.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL

# асинхронный движок и сессии
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

# базовый класс для моделей
Base = declarative_base()

async def init_db():
    """
    Создаёт все таблицы, описанные в моделях (Base.metadata),
    если их ещё нет.
    """
    async with engine.begin() as conn:
        # убедимся, что все модели импортированы до этой строки —
        # тогда metadata.create_all создаст все таблицы
        await conn.run_sync(Base.metadata.create_all)
