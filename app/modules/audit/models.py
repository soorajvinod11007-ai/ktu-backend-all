from __future__ import annotations
import enum, uuid
from typing import Any
from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class AuditAction(str, enum.Enum):
    CREATE  = 'create'
    UPDATE  = 'update'
    DELETE  = 'delete'
    RESTORE = 'restore'
    IMPORT  = 'import'
    EXPORT  = 'export'

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action: Mapped[AuditAction] = mapped_column(SAEnum(AuditAction, name='audit_action', native_enum=True, values_callable=lambda c: [m.value for m in c]), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    changes: Mapped[Any] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deleted_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index('ix_audit_logs_resource_created_at', 'resource', 'created_at'),)

__all__ = ['AuditLog', 'AuditAction']
