"""Authentication and session persistence models."""

from sqlalchemy import Boolean, Column, DDL, DateTime, String, Text, event

from backend.database import Base
from backend.models import utc_now
from backend.tenancy import OWNER_ID


class Account(Base):
    __tablename__ = "spend_accounts"
    id = Column(String(36), primary_key=True)
    username = Column(String(32), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class AccessSession(Base):
    __tablename__ = "spend_access_sessions"
    id = Column(String(64), primary_key=True)  # SHA-256 of a random session ID
    user_id = Column(String(36), nullable=False, default=OWNER_ID, index=True)
    password_version = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


for _auth_model in (AccessSession, Account):
    event.listen(
        _auth_model.__table__,
        "after_create",
        DDL("ALTER TABLE %(fullname)s ENABLE ROW LEVEL SECURITY").execute_if(dialect="postgresql"),
    )
