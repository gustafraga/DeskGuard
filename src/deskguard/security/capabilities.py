"""Políticas de capacidade e aprovação.

O DeskGuard separa duas coisas que costumam ser confundidas:

* *capacidade* — o que a ferramenta é capaz de fazer (leitura ou alteração);
* *aprovação* — a autorização explícita do operador para que uma alteração
  seja executada.

Um procedimento que declara capacidade ``MODIFYING`` nunca é executado sem
uma aprovação explícita e registrada na trilha de auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass

from deskguard.domain.enums import AuditAction, Capability
from deskguard.domain.spec import ProcedureSpec
from deskguard.errors import CapabilityDeniedError


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Resultado da verificação de autorização de uma operação."""

    allowed: bool
    requires_approval: bool
    reason: str

    def __bool__(self) -> bool:  # pragma: no cover - conveniência
        return self.allowed


class CapabilityPolicy:
    """Aplica as regras de menor privilégio sobre as capacidades do catálogo."""

    @staticmethod
    def requires_approval(spec: ProcedureSpec) -> bool:
        return spec.capability is Capability.MODIFYING

    @staticmethod
    def evaluate(spec: ProcedureSpec, approved: bool) -> ApprovalDecision:
        if spec.capability is Capability.READ_ONLY:
            return ApprovalDecision(
                allowed=True,
                requires_approval=False,
                reason="Procedimento somente leitura; nenhuma aprovação é necessária.",
            )
        if approved:
            return ApprovalDecision(
                allowed=True,
                requires_approval=True,
                reason="Aprovação explícita concedida pelo operador.",
            )
        return ApprovalDecision(
            allowed=False,
            requires_approval=True,
            reason=(
                f"O procedimento '{spec.id}' altera o sistema e exige confirmação "
                "explícita do operador antes de ser executado."
            ),
        )

    @staticmethod
    def authorize(spec: ProcedureSpec, approved: bool) -> ApprovalDecision:
        """Valida a autorização ou interrompe com ``CapabilityDeniedError``."""
        decision = CapabilityPolicy.evaluate(spec, approved)
        if not decision.allowed:
            raise CapabilityDeniedError(decision.reason)
        return decision

    @staticmethod
    def audit_action(spec: ProcedureSpec, approved: bool) -> AuditAction:
        if spec.capability is Capability.READ_ONLY:
            return AuditAction.EXECUTION_STARTED
        return (
            AuditAction.MUTATION_APPROVED
            if approved
            else AuditAction.MUTATION_REJECTED
        )
