"""Modelos de persistência (SQLAlchemy 2.0).

O esquema cobre três responsabilidades distintas:

* ``executions``      — o registro de cada execução de procedimento;
* ``execution_steps`` — o resultado de cada verificação individual;
* ``audit_events``    — a trilha append-only de ações realizadas na plataforma.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UtcDateTime(TypeDecorator):
    """Persistir datetimes sempre em UTC e devolvê-los com fuso horário."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")

    def process_result_value(self, value: str | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed


class Base(DeclarativeBase):
    pass


class ExecutionRow(Base):
    """Uma execução de procedimento."""

    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    procedure_id: Mapped[str] = mapped_column(String(80), index=True)
    procedure_title: Mapped[str] = mapped_column(String(200))
    procedure_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    capability: Mapped[str] = mapped_column(String(20), default="read_only")
    mode: Mapped[str] = mapped_column(String(10), default="live", index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    outcome: Mapped[str] = mapped_column(String(30), default="inconclusive", index=True)
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_version: Mapped[str] = mapped_column(String(20), default="0.0.0")
    host: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor: Mapped[str] = mapped_column(String(120), default="local")
    approval_granted: Mapped[bool] = mapped_column(Boolean, default=False)


class ExecutionStepRow(Base):
    """Resultado de uma verificação individual dentro de uma execução."""

    __tablename__ = "execution_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer, default=0)
    check_id: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditEventRow(Base):
    """Trilha de auditoria append-only."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    execution_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="local")
    action: Mapped[str] = mapped_column(String(60), index=True)
    target: Mapped[str] = mapped_column(String(200), default="")
    outcome: Mapped[str] = mapped_column(String(30), default="ok")
    mode: Mapped[str] = mapped_column(String(10), default="live")
    approval_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}")


def dumps_json(value: Any) -> str:
    """Serializa estruturas com segurança, sem quebrar em valores exóticos."""
    return json.dumps(value, ensure_ascii=False, default=str)


def loads_json(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}
