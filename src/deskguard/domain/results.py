"""Estruturas de resultado usadas pelo motor de execução.

O objetivo deste módulo é garantir que a diferença entre "problema confirmado"
e "verificação inconclusiva" nunca se perca na passagem entre as camadas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from deskguard.domain.enums import (
    CheckStatus,
    ExecutionMode,
    ExecutionStatus,
    Outcome,
    Severity,
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Resultado de uma verificação unitária (uma etapa de um procedimento)."""

    check_id: str
    title: str
    status: CheckStatus
    message: str
    severity: Severity = Severity.INFO
    evidence: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None
    error_code: str | None = None
    remediation: str | None = None
    simulated: bool = False

    @property
    def is_confirmed_problem(self) -> bool:
        return self.status.is_confirmed_problem

    @classmethod
    def ok(
        cls,
        check_id: str,
        title: str,
        message: str,
        *,
        evidence: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        simulated: bool = False,
    ) -> "CheckResult":
        return cls(
            check_id=check_id,
            title=title,
            status=CheckStatus.PASS,
            message=message,
            evidence=evidence or {},
            duration_ms=duration_ms,
            simulated=simulated,
        )

    @classmethod
    def fail(
        cls,
        check_id: str,
        title: str,
        message: str,
        *,
        severity: Severity = Severity.MEDIUM,
        evidence: dict[str, Any] | None = None,
        remediation: str | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
        simulated: bool = False,
    ) -> "CheckResult":
        return cls(
            check_id=check_id,
            title=title,
            status=CheckStatus.FAIL,
            message=message,
            severity=severity,
            evidence=evidence or {},
            remediation=remediation,
            duration_ms=duration_ms,
            error_code=error_code,
            simulated=simulated,
        )

    @classmethod
    def warning(
        cls,
        check_id: str,
        title: str,
        message: str,
        *,
        severity: Severity = Severity.LOW,
        evidence: dict[str, Any] | None = None,
        remediation: str | None = None,
        duration_ms: int | None = None,
        simulated: bool = False,
    ) -> "CheckResult":
        return cls(
            check_id=check_id,
            title=title,
            status=CheckStatus.WARN,
            message=message,
            severity=severity,
            evidence=evidence or {},
            remediation=remediation,
            duration_ms=duration_ms,
            simulated=simulated,
        )

    @classmethod
    def inconclusive(
        cls,
        check_id: str,
        title: str,
        message: str,
        *,
        error_code: str | None = None,
        evidence: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        simulated: bool = False,
    ) -> "CheckResult":
        """Resultado de uma verificação que não pôde ser concluída.

        Nunca deve ser usado para descrever um problema confirmado.
        """
        return cls(
            check_id=check_id,
            title=title,
            status=CheckStatus.INCONCLUSIVE,
            message=message,
            severity=Severity.INFO,
            evidence=evidence or {},
            duration_ms=duration_ms,
            error_code=error_code,
            simulated=simulated,
        )

    @classmethod
    def not_applicable(
        cls,
        check_id: str,
        title: str,
        message: str,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> "CheckResult":
        return cls(
            check_id=check_id,
            title=title,
            status=CheckStatus.NOT_APPLICABLE,
            message=message,
            evidence=evidence or {},
        )

    @classmethod
    def skipped(
        cls,
        check_id: str,
        title: str,
        message: str,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> "CheckResult":
        return cls(
            check_id=check_id,
            title=title,
            status=CheckStatus.SKIPPED,
            message=message,
            evidence=evidence or {},
        )


@dataclass(slots=True)
class ProcedureResult:
    """Resultado consolidado de uma execução de procedimento."""

    procedure_id: str
    procedure_title: str
    status: ExecutionStatus
    outcome: Outcome
    mode: ExecutionMode
    checks: list[CheckResult] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    simulated: bool = False

    @property
    def duration_ms(self) -> int | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)

    @property
    def confirmed_problems(self) -> list[CheckResult]:
        return [check for check in self.checks if check.status.is_confirmed_problem]

    @property
    def inconclusive_checks(self) -> list[CheckResult]:
        return [check for check in self.checks if check.status.is_inconclusive]


def aggregate_outcome(checks: list[CheckResult]) -> Outcome:
    """Deriva o consolidado de uma execução a partir das etapas.

    Regras:
      * qualquer desvio confirmado (FAIL/WARN) domina o resultado;
      * sem desvios, a existência de inconclusões torna o resultado inconclusivo;
      * caso contrário, o resultado é considerado saudável.
    """
    if not checks:
        return Outcome.INCONCLUSIVE
    if any(check.status.is_confirmed_problem for check in checks):
        return Outcome.ISSUES_FOUND
    if any(check.status.is_inconclusive for check in checks):
        return Outcome.INCONCLUSIVE
    return Outcome.HEALTHY
