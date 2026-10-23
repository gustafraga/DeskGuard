"""Serviço de execução de procedimentos.

Responsabilidades:

* validar parâmetros e capacidade antes de qualquer coleta;
* registrar o início e o fim da execução no banco e na trilha de auditoria;
* executar o procedimento fora do ciclo de requisição, para que a interface
  possa acompanhar o progresso sem bloquear;
* garantir que uma falha interna vire uma execução ``failed`` registrada,
  e nunca uma exceção silenciosa.
"""

from __future__ import annotations

import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from deskguard.catalog import registry
from deskguard.collectors.base import ProbeContext
from deskguard.config import Settings
from deskguard.domain.enums import AuditAction, ExecutionMode, ExecutionStatus, Outcome
from deskguard.domain.results import CheckResult, aggregate_outcome
from deskguard.security.allowlist import (
    TargetAllowlist,
    allowlist_path_for,
    load_allowlist,
)
from deskguard.security.capabilities import CapabilityPolicy
from deskguard.security.validation import validate_params
from deskguard.storage import repository
from deskguard.storage.database import Database
from deskguard.version import __version__


@dataclass(slots=True)
class ExecutionOutcome:
    """Resultado devuelto ao chamador após uma execução."""

    execution_id: str
    procedure_id: str
    status: ExecutionStatus
    outcome: Outcome
    checks: list[CheckResult]
    summary: str
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ExecutionService:
    """Coordena o ciclo de vida das execuções de procedimento."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, settings.max_concurrent_executions),
            thread_name_prefix="deskguard-exec",
        )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def submit(
        self,
        procedure_id: str,
        params: dict[str, Any] | None = None,
        *,
        mode: ExecutionMode | None = None,
        actor: str = "local",
        approved: bool = False,
    ) -> str:
        """Registra e agenda uma execução. Retorna o identificador."""
        spec = registry.get_spec(procedure_id)
        CapabilityPolicy.authorize(spec, approved)
        allowlist = load_allowlist(allowlist_path_for(self.settings.data_dir))
        clean_params = validate_params(spec, params, allowlist=allowlist)
        effective_mode = mode or self.settings.mode

        execution_id = str(uuid.uuid4())
        with self.db.session() as session:
            repository.create_execution(
                session,
                execution_id=execution_id,
                spec=spec,
                mode=effective_mode,
                params=clean_params,
                actor=actor,
                tool_version=__version__,
                host=socket.gethostname(),
                approval_granted=approved,
            )
            repository.record_audit(
                session,
                action=CapabilityPolicy.audit_action(spec, approved),
                actor=actor,
                target=f"{spec.id} ({spec.title})",
                outcome="accepted",
                mode=effective_mode,
                execution_id=execution_id,
                approval_granted=approved,
                details={"params": clean_params, "capability": str(spec.capability)},
            )

        self._pool.submit(
            self._run,
            execution_id,
            procedure_id,
            clean_params,
            effective_mode,
            actor,
            allowlist,
        )
        return execution_id

    def run_synchronously(
        self,
        procedure_id: str,
        params: dict[str, Any] | None = None,
        *,
        mode: ExecutionMode | None = None,
        actor: str = "local",
        approved: bool = False,
    ) -> ExecutionOutcome:
        """Executa o procedimento no próprio thread. Usado pela CLI e testes."""
        spec = registry.get_spec(procedure_id)
        CapabilityPolicy.authorize(spec, approved)
        allowlist = load_allowlist(allowlist_path_for(self.settings.data_dir))
        clean_params = validate_params(spec, params, allowlist=allowlist)
        effective_mode = mode or self.settings.mode

        execution_id = str(uuid.uuid4())
        with self.db.session() as session:
            repository.create_execution(
                session,
                execution_id=execution_id,
                spec=spec,
                mode=effective_mode,
                params=clean_params,
                actor=actor,
                tool_version=__version__,
                host=socket.gethostname(),
                approval_granted=approved,
            )
            repository.record_audit(
                session,
                action=CapabilityPolicy.audit_action(spec, approved),
                actor=actor,
                target=f"{spec.id} ({spec.title})",
                outcome="accepted",
                mode=effective_mode,
                execution_id=execution_id,
                approval_granted=approved,
                details={"params": clean_params, "capability": str(spec.capability)},
            )

        result = self._execute(
            execution_id, procedure_id, clean_params, effective_mode, actor, allowlist
        )
        return result

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=False)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _run(
        self,
        execution_id: str,
        procedure_id: str,
        params: dict[str, Any],
        mode: ExecutionMode,
        actor: str,
        allowlist: TargetAllowlist,
    ) -> None:
        try:
            self._execute(
                execution_id, procedure_id, params, mode, actor, allowlist
            )
        except Exception:  # noqa: BLE001 - a falha já foi registrada
            pass

    def _execute(
        self,
        execution_id: str,
        procedure_id: str,
        params: dict[str, Any],
        mode: ExecutionMode,
        actor: str,
        allowlist: TargetAllowlist,
    ) -> ExecutionOutcome:
        started_at = repository.utcnow()
        with self.db.session() as session:
            repository.mark_running(session, execution_id, started_at)

        checks: list[CheckResult] = []
        outcome = Outcome.ERROR
        status = ExecutionStatus.FAILED
        error: str | None = None

        try:
            factory = registry.get_factory(procedure_id)
            procedure = factory().for_mode(mode)
            context = ProbeContext(
                execution_id=execution_id,
                mode=mode,
                timeout_s=self.settings.request_timeout_s,
                params=params,
                shared={"allowlist": allowlist},
            )
            checks = procedure.run(context)
            outcome = aggregate_outcome(checks)
            status = ExecutionStatus.COMPLETED
        except Exception as exc:  # noqa: BLE001 - fronteira de isolamento
            error = f"{type(exc).__name__}: {exc}"

        summary = repository.summarize_checks(checks)
        finished_at = repository.utcnow()

        with self.db.session() as session:
            repository.finish_execution(
                session,
                execution_id,
                status=str(status),
                outcome=str(outcome),
                checks=checks,
                summary=summary,
                error=error,
                finished_at=finished_at,
            )
            repository.record_audit(
                session,
                action=AuditAction.EXECUTION_FINISHED,
                actor=actor,
                target=procedure_id,
                outcome=str(outcome),
                mode=mode,
                execution_id=execution_id,
                details={
                    "status": str(status),
                    "checks": len(checks),
                    "error": error,
                },
            )

        return ExecutionOutcome(
            execution_id=execution_id,
            procedure_id=procedure_id,
            status=status,
            outcome=outcome,
            checks=checks,
            summary=summary,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
        )
