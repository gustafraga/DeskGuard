"""Rotas do Módulo G - Auto-Remediação."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from deskguard.api.deps import CSRFDependency
from deskguard.remediation.actions import REMEDIATION_ACTIONS
from deskguard.remediation.service import RemediationService

router = APIRouter(prefix="/remediation", tags=["remediação"])


class RemediateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str = Field(min_length=3, max_length=80)
    approved: bool = False
    confirmation_text: str | None = Field(default=None, max_length=200)


class RemediateResponse(BaseModel):
    action_id: str
    status: str
    approved: bool
    result: dict


@router.get("/actions")
def list_actions() -> dict:
    actions = []
    for action in REMEDIATION_ACTIONS.values():
        actions.append(
            {
                "action_id": action.action_id,
                "title": action.title,
                "description": action.description,
                "service_name": action.service_name,
                "requires_admin": action.requires_admin,
                "risk_level": action.risk_level,
            }
        )
    return {"actions": actions, "count": len(actions)}


@router.post("/execute", response_model=RemediateResponse)
def execute_remediation(payload: RemediateRequest, _csrf: None = CSRFDependency) -> dict:
    if not payload.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ação requer confirmação explícita do usuário.",
        )

    service = RemediationService()
    try:
        result = service.execute(payload.action_id, approved=True)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
