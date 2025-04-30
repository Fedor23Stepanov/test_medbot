# db/models.py

import enum
import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    JSON,
    ForeignKey,
    Enum as SQLEnum,
    Boolean,
)
from sqlalchemy.orm import relationship
from .database import Base


class UserStatus(enum.Enum):
    pending = "pending"   # ожидает первого сообщения
    active  = "active"    # активен, может пользоваться ботом
    blocked = "blocked"   # заблокирован, бот игнорирует


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    tg_id         = Column(Integer, unique=True, index=True, nullable=True)
    username      = Column(String, unique=True, index=True, nullable=False)
    role          = Column(String, nullable=False, default="User")
    status        = Column(SQLEnum(UserStatus), nullable=False, default=UserStatus.pending)
    invited_by    = Column(Integer, nullable=True)  # Telegram ID пригласившего
    created_at    = Column(DateTime, default=datetime.datetime.utcnow)
    activated_at  = Column(DateTime, nullable=True)

    events = relationship(
        "Event",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class DeviceOption(Base):
    __tablename__ = "device_options"

    id       = Column(Integer, primary_key=True, index=True)
    ua       = Column(String, nullable=False)
    css_size = Column(JSON, nullable=False)   # [width, height]
    platform = Column(String, nullable=False)
    dpr      = Column(Integer, nullable=False)
    mobile   = Column(Boolean, nullable=False)
    model    = Column(String, nullable=True)

    events = relationship(
        "Event",
        back_populates="device_option",
        cascade="all, delete-orphan",
    )


class ProxyLog(Base):
    __tablename__ = "proxy_logs"

    id        = Column(Integer, primary_key=True, index=True)
    attempt   = Column(Integer, nullable=False)
    ip        = Column(String, nullable=True)
    city      = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)


class Event(Base):
    __tablename__ = "events"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_option_id = Column(Integer, ForeignKey("device_options.id", ondelete="SET NULL"), nullable=False, index=True)
    state            = Column(String, nullable=False)
    initial_url      = Column(String, nullable=False)
    final_url        = Column(String, nullable=False)
    ip               = Column(String, nullable=True)
    isp              = Column(String, nullable=True)
    timestamp        = Column(DateTime, default=datetime.datetime.utcnow)

    user          = relationship("User", back_populates="events")
    device_option = relationship("DeviceOption", back_populates="events")
