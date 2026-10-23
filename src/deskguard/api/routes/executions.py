"""Rotas de execução de procedimentos e consulta ao histórico."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from deskguard.api.deps import CSRFDependency, get_database, get_execution_service
from deskguard.api.schemas import ExecutionAcceptedResponse, RunExecutionRequest
from deskguard.catalog import registry
from deskguard.domain.enums import ExecutionMode
from deskguard.errors import (
    CapabilityDeniedError,
    InvalidParametersError,
    ProcedureNotFoundError,
)
from deskguard.services.execution import ExecutionService
from deskguard.services.presentation import build_execution_presentation
from deskguard.storage import repository
from deskguard.storage.database import Database

router = APIRouter(prefix="/executions", tags=["execuções"])


@router.get("")
def list_executions(
    db: Database = Depends(get_database),
    query: str | None = Query(default=None, max_length=120),
    procedure_id: str | None = Query(default=None, max_length=80),
    status_filter: str | None = Query(default=None, alias="status", max_length=30),
    outcome: str | None = Query(default=None, max_length=30),
    mode: str | None = Query(default=None, max_length=10),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Histórico de execuções com busca textual."""
    with db.session() as session:
        rows = repository.list_executions(
            session,
            query=query,
            procedure_id=procedure_id,
            status=status_filter,
            outcome=outcome,
            mode=mode,
            limit=limit,
            offset=offset,
        )
        total = repository.count_executions(
            session,
            query=query,
            procedure_id=procedure_id,
            status=status_filter,
            outcome=outcome,
            mode=mode,
        )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "executions": [repository.execution_to_dict(row) for row in rows],
    }


@router.get("/{execution_id}")
def get_execution(execution_id: str, db: Database = Depends(get_database)) -> dict:
    """Detalhe de uma execução, com todas as etapas realizadas."""
    with db.session() as session:
        row = repository.get_execution(session, execution_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execução não encontrada.",
            )
        steps = repository.get_steps(session, execution_id)
        payload = repository.execution_to_dict(row)
        payload["steps"] = [repository.step_to_dict(step) for step in steps]

    presentation = build_execution_presentation(payload, payload["steps"])
    payload["presentation"] = presentation
    for step, section in zip(payload["steps"], presentation["sections"]):
        step["technical_sections"] = section["tables"]

    try:
        payload["procedure"] = registry.get_spec(payload["procedure_id"]).to_dict()
    except ProcedureNotFoundError:
        payload["procedure"] = None
    return payload


@router.post("", response_model=ExecutionAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
def run_procedure(
    payload: RunExecutionRequest,
    service: ExecutionService = Depends(get_execution_service),
    _csrf: None = CSRFDependency,
) -> dict:
    """Agenda a execução de um procedimento e devolve o identificador."""
    registry.load_builtin_procedures()
    mode = ExecutionMode(payload.mode)
    try:
        execution_id = service.submit(
            payload.procedure_id,
            payload.params,
            mode=mode,
            approved=payload.approved,
        )
    except ProcedureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except InvalidParametersError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CapabilityDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc

    return {
        "execution_id": execution_id,
        "status": "queued",
        "procedure_id": payload.procedure_id,
    }
