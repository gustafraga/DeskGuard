"""Ações de remediação disponíveis no Módulo G."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RemediationActionId(StrEnum):
    RESTART_SPOOLER = "remediate.restart_spooler"


@dataclass(frozen=True, slots=True)
class RemediationAction:
    action_id: str
    title: str
    description: str
    service_name: str | None
    requires_admin: bool
    script_name: str
    risk_level: str


REMEDIATION_ACTIONS: dict[str, RemediationAction] = {
    RemediationActionId.RESTART_SPOOLER: RemediationAction(
        action_id=RemediationActionId.RESTART_SPOOLER,
        title="Reiniciar o serviço Print Spooler",
        description=(
            "Reinicia o serviço Print Spooler (fila de impressão). "
            "Útil quando há trabalhos travados na fila ou a impressora não responde."
        ),
        service_name="Spooler",
        requires_admin=False,
        script_name="remediation/restart_spooler.ps1",
        risk_level="low",
    ),
}
