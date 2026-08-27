from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.users.models import User


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "octet_length(token_hash) = 32",
            name="ck_sessions_token_hash_length",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_sessions_expires_after_creation",
        ),
        UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        PrimaryKeyConstraint("id", name="pk_sessions"),
        Index("ix_sessions_user_id_revoked_at", "user_id", "revoked_at"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "users.id",
            name="fk_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class AuthThrottleBucket(Base):
    __tablename__ = "auth_throttle_buckets"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('account', 'ip')",
            name="ck_auth_throttle_buckets_scope",
        ),
        CheckConstraint(
            "octet_length(key_hash) = 32",
            name="ck_auth_throttle_buckets_key_hash_length",
        ),
        CheckConstraint(
            "failure_count >= 0",
            name="ck_auth_throttle_buckets_failure_count_nonnegative",
        ),
        UniqueConstraint(
            "scope",
            "key_hash",
            name="uq_auth_throttle_buckets_scope_key_hash",
        ),
        PrimaryKeyConstraint("id", name="pk_auth_throttle_buckets"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
