"""Serviço de execução de ações de remediação."""

from __future__ import annotations

import json
from typing import Any

from deskguard.collectors.powershell import PowerShellRunner, script_path
from deskguard.errors import CollectorError
from deskguard.remediation.actions import REMEDIATION_ACTIONS


class RemediationService:
    def __init__(self) -> None:
        self.runner = PowerShellRunner()

    def execute(self, action_id: str, approved: bool, actor: str = "local") -> dict[str, Any]:
        if not approved:
            raise ValueError("Ação requer confirmação explícita do usuário.")

        action = REMEDIATION_ACTIONS.get(action_id)
        if action is None:
            raise ValueError(f"Ação de remediação não encontrada: {action_id}")

        script = script_path(action.script_name)
        outcome = self.runner.run_script(script, {"approved": True}, timeout_s=30.0)
        
        if outcome.ok and outcome.payload.get("ok"):
            return {
                "action_id": action_id,
                "status": "completed",
                "approved": True,
                "actor": actor,
                "result": outcome.payload.get("data", {}),
            }
        raise CollectorError(
            outcome.payload.get("message") or "Falha na execução da remediação."
        )
