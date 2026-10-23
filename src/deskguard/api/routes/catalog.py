"""Rotas do catálogo de procedimentos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from deskguard.api.deps import get_database
from deskguard.catalog import registry
from deskguard.domain.enums import AuditAction
from deskguard.storage import repository
from deskguard.storage.database import Database

router = APIRouter(prefix="/procedures", tags=["catálogo"])

_CATEGORY_LABELS = {
    "Sistema": "Sistema e inventário",
    "Rede": "Rede e conectividade",
    "Impressoras": "Impressoras e filas",
    "Serviços": "Serviços e aplicativos",
    "Desempenho": "Desempenho e recursos",
    "Segurança": "Segurança e auditoria",
}


@router.get("")
def list_procedures(db: Database = Depends(get_database)) -> dict:
    """Catálogo completo, agrupado por categoria."""
    registry.load_builtin_procedures()
    specs = registry.list_specs()

    grouped: dict[str, list[dict]] = {}
    for spec in specs:
        grouped.setdefault(spec.category, []).append(spec.to_dict())

    categories = [
        {
            "id": category,
            "label": _CATEGORY_LABELS.get(category, category),
            "count": len(items),
            "procedure_ids": [item["id"] for item in items],
        }
        for category, items in sorted(grouped.items())
    ]

    with db.session() as session:
        repository.record_audit(
            session,
            action=AuditAction.CATALOG_VIEWED,
            target="catalog",
            outcome="ok",
            details={"count": len(specs)},
        )

    return {
        "count": len(specs),
        "categories": categories,
        "procedures": [spec.to_dict() for spec in specs],
    }


@router.get("/{procedure_id}")
def get_procedure(procedure_id: str) -> dict:
    """Detalhe de um procedimento, incluindo etapas e parâmetros aceitos."""
    registry.load_builtin_procedures()
    try:
        spec = registry.get_spec(procedure_id)
    except Exception as exc:  # ProcedureNotFoundError
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procedimento '{procedure_id}' não encontrado.",
        ) from exc
    return spec.to_dict()
