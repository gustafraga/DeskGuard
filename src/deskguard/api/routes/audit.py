"""Rotas de consulta à trilha de auditoria."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from deskguard.api.deps import get_database
from deskguard.storage import repository
from deskguard.storage.database import Database

router = APIRouter(prefix="/audit", tags=["auditoria"])


@router.get("")
def list_audit(
    db: Database = Depends(get_database),
    query: str | None = Query(default=None, max_length=120),
    action: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Registros de auditoria, dos mais recentes para os mais antigos."""
    with db.session() as session:
        rows = repository.list_audit(
            session, query=query, action=action, limit=limit, offset=offset
        )
    return {
        "count": len(rows),
        "events": [repository.audit_to_dict(row) for row in rows],
    }
