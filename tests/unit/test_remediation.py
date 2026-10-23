"""Testes do Módulo G - Auto-Remediação."""

from __future__ import annotations

from deskguard.remediation.actions import REMEDIATION_ACTIONS, RemediationActionId
from deskguard.remediation.service import RemediationService


def test_remediation_actions_exist():
    assert RemediationActionId.RESTART_SPOOLER in REMEDIATION_ACTIONS
    action = REMEDIATION_ACTIONS[RemediationActionId.RESTART_SPOOLER]
    assert action.title
    assert action.requires_admin is False or action.requires_admin is True


def test_remediation_service_requires_approval():
    service = RemediationService()
    try:
        service.execute("remediate.restart_spooler", approved=False)
        assert False, "Should raise"
    except ValueError as exc:
        assert "confirmação" in str(exc).lower()
