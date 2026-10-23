"""Vocabulário de domínio do DeskGuard.

Este módulo centraliza os estados e classificações usados por todo o sistema.
A separação entre *status de uma verificação* e *severidade do problema* é
proposital: uma verificação inconclusiva (por falta de permissão, por exemplo)
não pode ser apresentada como uma falha confirmada.
"""

from __future__ import annotations

from enum import StrEnum


class CheckStatus(StrEnum):
    """Resultado de uma verificação individual dentro de um procedimento."""

    PASS = "pass"
    """A verificação foi executada e não encontrou desvio."""

    FAIL = "fail"
    """A verificação foi executada e confirmou a existência de um problema."""

    WARN = "warn"
    """A verificação foi executada e encontrou um desvio de menor impacto."""

    INCONCLUSIVE = "inconclusive"
    """Não foi possível determinar o estado (permissão, indisponibilidade, timeout)."""

    NOT_APPLICABLE = "not_applicable"
    """A verificação não se aplica a este endpoint ou a esta configuração."""

    SKIPPED = "skipped"
    """A verificação foi dispensada porque um pré-requisito não foi satisfeito."""

    @property
    def is_confirmed_problem(self) -> bool:
        """Verdadeiro somente para desvios efetivamente confirmados."""
        return self in (CheckStatus.FAIL, CheckStatus.WARN)

    @property
    def is_inconclusive(self) -> bool:
        return self in (CheckStatus.INCONCLUSIVE, CheckStatus.SKIPPED)


class Severity(StrEnum):
    """Severidade atribuída a um desvio confirmado."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
        }[self]

    @classmethod
    def max(cls, values: "list[Severity] | tuple[Severity, ...]") -> Severity:
        if not values:
            return Severity.INFO
        return max(values, key=lambda item: item.rank)


class Capability(StrEnum):
    """Natureza da operação executada por um procedimento."""

    READ_ONLY = "read_only"
    """Somente leitura: consulta o estado do sistema sem alterá-lo."""

    MODIFYING = "modifying"
    """Altera o estado do sistema e exige aprovação explícita do operador."""


class PrivilegeLevel(StrEnum):
    """Nível de privilégio exigido pelo procedimento."""

    USER = "user"
    """Executável com a conta do usuário logado."""

    ELEVATED = "elevated"
    """Pode exigir elevação; quando indisponível, o resultado vira inconclusivo."""


class ExecutionStatus(StrEnum):
    """Ciclo de vida de uma execução."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionMode(StrEnum):
    """Origem dos dados de uma execução."""

    LIVE = "live"
    """Dados coletados do sistema real do usuário."""

    DEMO = "demo"
    """Dados simulados para demonstração, sempre identificados como tal."""


class Outcome(StrEnum):
    """Consolidado de uma execução inteira."""

    HEALTHY = "healthy"
    """Nenhum desvio confirmado e nenhuma inconclusividade relevante."""

    ISSUES_FOUND = "issues_found"
    """Houve ao menos um desvio confirmado."""

    INCONCLUSIVE = "inconclusive"
    """Não foi possível avaliar o estado com confiança suficiente."""

    ERROR = "error"
    """A execução não pôde ser concluída por erro técnico."""


class AuditAction(StrEnum):
    """Ações registradas na trilha de auditoria."""

    EXECUTION_STARTED = "execution.started"
    EXECUTION_FINISHED = "execution.finished"
    REPORT_EXPORTED = "report.exported"
    CATALOG_VIEWED = "catalog.viewed"
    SETTINGS_VIEWED = "settings.viewed"
    MUTATION_REQUESTED = "mutation.requested"
    MUTATION_APPROVED = "mutation.approved"
    MUTATION_REJECTED = "mutation.rejected"
