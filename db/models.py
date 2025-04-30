# db/models.py

import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    role       = Column(String, nullable=False, default="User")
    tg_id      = Column(Integer, unique=True, index=True, nullable=False)
    username   = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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
    state            = Column(String, nullable=False)
    device_option_id = Column(Integer, ForeignKey("device_options.id", ondelete="SET NULL"), nullable=False, index=True)
    initial_url      = Column(String, nullable=False)
    final_url        = Column(String, nullable=False)
    ip               = Column(String, nullable=True)
    isp              = Column(String, nullable=True)
    timestamp        = Column(DateTime, default=datetime.datetime.utcnow)

    user          = relationship("User", back_populates="events")
    device_option = relationship("DeviceOption", back_populates="events")
