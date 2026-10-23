"""Repositório de dados do DeskGuard.

Toda a leitura e escrita no banco passa por estas funções. Nenhuma camada
superior (API, serviços, interface) constrói consultas SQL diretamente.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deskguard.domain.enums import AuditAction, CheckStatus, ExecutionMode, Severity
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ProcedureSpec
from deskguard.storage.models import (
    AuditEventRow,
    ExecutionRow,
    ExecutionStepRow,
    dumps_json,
    loads_json,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Execuções
# --------------------------------------------------------------------------
def create_execution(
    session: Session,
    *,
    execution_id: str,
    spec: ProcedureSpec,
    mode: ExecutionMode,
    params: dict[str, Any],
    actor: str = "local",
    tool_version: str = "0.0.0",
    host: str | None = None,
    approval_granted: bool = False,
) -> ExecutionRow:
    row = ExecutionRow(
        id=execution_id,
        procedure_id=spec.id,
        procedure_title=spec.title,
        procedure_version=spec.version,
        capability=str(spec.capability),
        mode=str(mode),
        status="queued",
        outcome="inconclusive",
        params_json=dumps_json(params),
        tool_version=tool_version,
        host=host,
        actor=actor,
        approval_granted=approval_granted,
    )
    session.add(row)
    session.flush()
    return row


def mark_running(session: Session, execution_id: str, started_at: datetime) -> None:
    row = session.get(ExecutionRow, execution_id)
    if row is None:
        return
    row.status = "running"
    row.started_at = started_at
    session.flush()


def finish_execution(
    session: Session,
    execution_id: str,
    *,
    status: str,
    outcome: str,
    checks: Sequence[CheckResult],
    summary: str,
    error: str | None = None,
    finished_at: datetime | None = None,
) -> ExecutionRow | None:
    row = session.get(ExecutionRow, execution_id)
    if row is None:
        return None

    finished = finished_at or utcnow()
    row.status = status
    row.outcome = outcome
    row.summary = summary
    row.error = error
    row.finished_at = finished
    if row.started_at is None:
        # Uma execução que chegou ao fim sem marcação de início (por exemplo,
        # em uma correção pontual de dados) ainda precisa ser datada para
        # aparecer nas janelas de tempo do painel.
        row.started_at = finished
    row.duration_ms = int((finished - row.started_at).total_seconds() * 1000)

    session.query(ExecutionStepRow).filter(
        ExecutionStepRow.execution_id == execution_id
    ).delete()

    for index, check in enumerate(checks):
        session.add(
            ExecutionStepRow(
                execution_id=execution_id,
                seq=index,
                check_id=check.check_id,
                title=check.title,
                status=str(check.status),
                severity=str(check.severity),
                message=check.message,
                evidence_json=dumps_json(check.evidence),
                duration_ms=check.duration_ms,
                error_code=check.error_code,
                remediation=check.remediation,
                simulated=check.simulated,
            )
        )
    session.flush()
    return row


def get_execution(session: Session, execution_id: str) -> ExecutionRow | None:
    return session.get(ExecutionRow, execution_id)


def get_steps(session: Session, execution_id: str) -> list[ExecutionStepRow]:
    return list(
        session.scalars(
            select(ExecutionStepRow)
            .where(ExecutionStepRow.execution_id == execution_id)
            .order_by(ExecutionStepRow.seq)
        )
    )


def list_executions(
    session: Session,
    *,
    query: str | None = None,
    procedure_id: str | None = None,
    status: str | None = None,
    outcome: str | None = None,
    mode: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ExecutionRow]:
    statement = select(ExecutionRow)
    if query:
        pattern = f"%{query.lower()}%"
        statement = statement.where(
            func.lower(ExecutionRow.procedure_title).like(pattern)
            | func.lower(ExecutionRow.procedure_id).like(pattern)
            | func.lower(ExecutionRow.summary).like(pattern)
            | func.lower(ExecutionRow.id).like(pattern)
        )
    if procedure_id:
        statement = statement.where(ExecutionRow.procedure_id == procedure_id)
    if status:
        statement = statement.where(ExecutionRow.status == status)
    if outcome:
        statement = statement.where(ExecutionRow.outcome == outcome)
    if mode:
        statement = statement.where(ExecutionRow.mode == mode)

    statement = (
        statement.order_by(ExecutionRow.started_at.desc(), ExecutionRow.id.desc())
        .limit(max(1, min(limit, 500)))
        .offset(max(0, offset))
    )
    return list(session.scalars(statement))


def count_executions(
    session: Session,
    *,
    query: str | None = None,
    procedure_id: str | None = None,
    status: str | None = None,
    outcome: str | None = None,
    mode: str | None = None,
) -> int:
    statement = select(func.count()).select_from(ExecutionRow)
    if query:
        pattern = f"%{query.lower()}%"
        statement = statement.where(
            func.lower(ExecutionRow.procedure_title).like(pattern)
            | func.lower(ExecutionRow.procedure_id).like(pattern)
            | func.lower(ExecutionRow.summary).like(pattern)
            | func.lower(ExecutionRow.id).like(pattern)
        )
    if procedure_id:
        statement = statement.where(ExecutionRow.procedure_id == procedure_id)
    if status:
        statement = statement.where(ExecutionRow.status == status)
    if outcome:
        statement = statement.where(ExecutionRow.outcome == outcome)
    if mode:
        statement = statement.where(ExecutionRow.mode == mode)
    return int(session.scalar(statement) or 0)


# --------------------------------------------------------------------------
# Auditoria
# --------------------------------------------------------------------------
def record_audit(
    session: Session,
    *,
    action: AuditAction | str,
    actor: str = "local",
    target: str = "",
    outcome: str = "ok",
    mode: ExecutionMode = ExecutionMode.LIVE,
    execution_id: str | None = None,
    approval_granted: bool = False,
    details: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> AuditEventRow:
    row = AuditEventRow(
        occurred_at=occurred_at or utcnow(),
        execution_id=execution_id,
        actor=actor,
        action=str(action),
        target=target[:200],
        outcome=outcome,
        mode=str(mode),
        approval_granted=approval_granted,
        details_json=dumps_json(details or {}),
    )
    session.add(row)
    session.flush()
    return row


def list_audit(
    session: Session,
    *,
    query: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEventRow]:
    statement = select(AuditEventRow)
    if query:
        pattern = f"%{query.lower()}%"
        statement = statement.where(
            func.lower(AuditEventRow.action).like(pattern)
            | func.lower(AuditEventRow.target).like(pattern)
            | func.lower(AuditEventRow.actor).like(pattern)
            | func.lower(AuditEventRow.execution_id).like(pattern)
        )
    if action:
        statement = statement.where(AuditEventRow.action == action)
    statement = (
        statement.order_by(AuditEventRow.occurred_at.desc(), AuditEventRow.id.desc())
        .limit(max(1, min(limit, 500)))
        .offset(max(0, offset))
    )
    return list(session.scalars(statement))


# --------------------------------------------------------------------------
# Indicadores do painel
# --------------------------------------------------------------------------
def dashboard_stats(session: Session) -> dict[str, Any]:
    """Calcula os indicadores do painel a partir dos dados reais gravados."""
    total = int(session.scalar(select(func.count()).select_from(ExecutionRow)) or 0)

    since = utcnow() - timedelta(hours=24)
    last_24h = int(
        session.scalar(
            select(func.count())
            .select_from(ExecutionRow)
            .where(ExecutionRow.started_at >= since)
        )
        or 0
    )

    by_status: dict[str, int] = {}
    for status, count in session.execute(
        select(ExecutionRow.status, func.count()).group_by(ExecutionRow.status)
    ):
        by_status[status] = int(count)

    by_outcome: dict[str, int] = {}
    for outcome, count in session.execute(
        select(ExecutionRow.outcome, func.count()).group_by(ExecutionRow.outcome)
    ):
        by_outcome[outcome] = int(count)

    by_procedure: list[dict[str, Any]] = [
        {"procedure_id": procedure_id, "title": title, "executions": int(count)}
        for procedure_id, title, count in session.execute(
            select(
                ExecutionRow.procedure_id,
                func.max(ExecutionRow.procedure_title),
                func.count(),
            )
            .group_by(ExecutionRow.procedure_id)
            .order_by(func.count().desc())
        )
    ]

    confirmed = int(
        session.scalar(
            select(func.count())
            .select_from(ExecutionStepRow)
            .where(ExecutionStepRow.status.in_([str(CheckStatus.FAIL), str(CheckStatus.WARN)]))
        )
        or 0
    )
    inconclusive = int(
        session.scalar(
            select(func.count())
            .select_from(ExecutionStepRow)
            .where(
                ExecutionStepRow.status.in_(
                    [str(CheckStatus.INCONCLUSIVE), str(CheckStatus.SKIPPED)]
                )
            )
        )
        or 0
    )

    by_severity: dict[str, int] = {}
    for severity, count in session.execute(
        select(ExecutionStepRow.severity, func.count())
        .where(ExecutionStepRow.status.in_([str(CheckStatus.FAIL), str(CheckStatus.WARN)]))
        .group_by(ExecutionStepRow.severity)
    ):
        by_severity[severity] = int(count)

    last_execution = session.scalars(
        select(ExecutionRow).order_by(ExecutionRow.started_at.desc()).limit(1)
    ).first()

    severidades: list[Severity] = []
    for chave in by_severity:
        try:
            severidades.append(Severity(chave))
        except ValueError:
            # Severidade desconhecida vinda de uma versão futura do formato.
            continue
    maior_severidade = (
        max(severidades, key=lambda item: item.rank).value if severidades else None
    )

    return {
        "total_executions": total,
        "executions_24h": last_24h,
        "by_status": by_status,
        "by_outcome": by_outcome,
        "by_procedure": by_procedure,
        "confirmed_issues": confirmed,
        "inconclusive_checks": inconclusive,
        "by_severity": by_severity,
        "last_execution_at": last_execution.started_at.isoformat()
        if last_execution and last_execution.started_at
        else None,
        "max_severity": maior_severidade,
    }


def summarize_checks(checks: Sequence[CheckResult]) -> str:
    """Texto curto que resume uma execução, usado no histórico."""
    if not checks:
        return "Nenhuma verificação executada."
    confirmed = sum(1 for check in checks if check.status.is_confirmed_problem)
    inconclusive = sum(1 for check in checks if check.status.is_inconclusive)
    passed = sum(
        1 for check in checks if check.status is CheckStatus.PASS
    )
    parts = [f"{len(checks)} verificação(ões)", f"{passed} aprovada(s)"]
    if confirmed:
        parts.append(f"{confirmed} desvio(s) confirmado(s)")
    if inconclusive:
        parts.append(f"{inconclusive} inconclusiva(s)")
    return " · ".join(parts)


def step_to_dict(row: ExecutionStepRow) -> dict[str, Any]:
    return {
        "check_id": row.check_id,
        "title": row.title,
        "status": row.status,
        "severity": row.severity,
        "message": row.message,
        "evidence": loads_json(row.evidence_json),
        "duration_ms": row.duration_ms,
        "error_code": row.error_code,
        "remediation": row.remediation,
        "simulated": bool(row.simulated),
    }


def execution_to_dict(row: ExecutionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "procedure_id": row.procedure_id,
        "procedure_title": row.procedure_title,
        "procedure_version": row.procedure_version,
        "capability": row.capability,
        "mode": row.mode,
        "status": row.status,
        "outcome": row.outcome,
        "params": loads_json(row.params_json),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": row.duration_ms,
        "summary": row.summary,
        "error": row.error,
        "tool_version": row.tool_version,
        "host": row.host,
        "actor": row.actor,
        "approval_granted": bool(row.approval_granted),
    }


def audit_to_dict(row: AuditEventRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "execution_id": row.execution_id,
        "actor": row.actor,
        "action": row.action,
        "target": row.target,
        "outcome": row.outcome,
        "mode": row.mode,
        "approval_granted": bool(row.approval_granted),
        "details": loads_json(row.details_json),
    }
