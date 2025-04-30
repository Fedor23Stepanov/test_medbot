# db/database.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL

# Создаём асинхронный движок SQLAlchemy
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

# Фабрика для создания асинхронных сессий
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Базовый класс для моделей
Base = declarative_base()

async def init_db():
    """
    Инициализирует БД: создаёт все таблицы, описанные в моделях.
    """
    # Импортируем модели, чтобы SQLAlchemy их зарегистрировал
    import db.models  # noqa: F401

    # Создаём таблицы в БД
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
