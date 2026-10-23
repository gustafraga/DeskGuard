"""Camada de domínio: vocabulário, resultados e especificações."""

from deskguard.domain.enums import (
    AuditAction,
    Capability,
    CheckStatus,
    ExecutionMode,
    ExecutionStatus,
    Outcome,
    PrivilegeLevel,
    Severity,
)
from deskguard.domain.results import CheckResult, ProcedureResult, aggregate_outcome
from deskguard.domain.spec import ParamSpec, ProcedureSpec, StepSpec

__all__ = [
    "AuditAction",
    "Capability",
    "CheckResult",
    "CheckStatus",
    "ExecutionMode",
    "ExecutionStatus",
    "Outcome",
    "ParamSpec",
    "PrivilegeLevel",
    "ProcedureResult",
    "ProcedureSpec",
    "Severity",
    "StepSpec",
    "aggregate_outcome",
]
