"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, IdMixin, JSONType, TimestampMixin, UTCDateTime, utcnow


class User(IdMixin, TimestampMixin, Base):
    """A farmer. Guests are identified by the SHA-256 of a random token, never the token itself."""

    __tablename__ = "users"

    guest_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    preferred_language: Mapped[str] = mapped_column(String(40), default="English")

    farms: Mapped[list["Farm"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Farm(IdMixin, TimestampMixin, Base):
    __tablename__ = "farms"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(120))
    location_name: Mapped[str | None] = mapped_column(String(160))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    size_value: Mapped[float | None] = mapped_column(Float)
    area_unit: Mapped[str | None] = mapped_column(String(20))
    soil_type: Mapped[str | None] = mapped_column(String(40))

    user: Mapped[User] = relationship(back_populates="farms")
    crops: Mapped[list["FarmCrop"]] = relationship(
        back_populates="farm",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FarmCrop.created_at",
    )


class FarmCrop(IdMixin, TimestampMixin, Base):
    __tablename__ = "farm_crops"

    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True
    )
    crop: Mapped[str] = mapped_column(String(40))
    variety: Mapped[str | None] = mapped_column(String(80))
    sowing_date: Mapped[date | None] = mapped_column(Date)
    growth_stage: Mapped[str | None] = mapped_column(String(40))
    irrigation_method: Mapped[str | None] = mapped_column(String(40))

    farm: Mapped[Farm] = relationship(back_populates="crops")


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    farm_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("farms.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(160))

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )


class Message(IdMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    advice: Mapped[dict | None] = mapped_column(JSONType)
    tool_log: Mapped[list | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Recommendation(IdMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (Index("ix_recommendations_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    farm_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("farms.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    origin: Mapped[str] = mapped_column(String(32))
    intent: Mapped[str] = mapped_column(String(40))
    crop: Mapped[str | None] = mapped_column(String(40))
    recommendation: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[str] = mapped_column(String(20))
    advice: Mapped[dict] = mapped_column(JSONType)
    weather_provenance: Mapped[str | None] = mapped_column(String(16))
    weather_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WeatherCache(IdMixin, Base):
    __tablename__ = "weather_cache"
    __table_args__ = (UniqueConstraint("cache_key"),)

    cache_key: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONType)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


__all__ = [
    "Base",
    "Conversation",
    "Farm",
    "FarmCrop",
    "Message",
    "Recommendation",
    "User",
    "WeatherCache",
]
