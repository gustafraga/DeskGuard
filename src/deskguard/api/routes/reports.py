"""Rotas de geração e exportação de relatórios técnicos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from deskguard.api.deps import CSRFDependency, get_database
from deskguard.api.schemas import ExportReportRequest
from deskguard.catalog import registry
from deskguard.domain.enums import AuditAction
from deskguard.errors import ProcedureNotFoundError
from deskguard.services.presentation import build_execution_presentation
from deskguard.services.report import build_report_markdown, build_report_text
from deskguard.storage import repository
from deskguard.storage.database import Database

router = APIRouter(prefix="/executions", tags=["relatórios"])


@router.get("/{execution_id}/report")
def get_report(execution_id: str, db: Database = Depends(get_database)) -> dict:
    """Relatório técnico em Markdown, pronto para edição pelo operador."""
    with db.session() as session:
        row = repository.get_execution(session, execution_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execução não encontrada.",
            )
        steps = repository.get_steps(session, execution_id)

    try:
        spec = registry.get_spec(row.procedure_id)
    except ProcedureNotFoundError:
        spec = None

    markdown = build_report_markdown(row, steps, spec)
    copy_markdown = build_report_markdown(
        row, steps, spec, include_dev_details=False
    )
    presentation = build_execution_presentation(
        repository.execution_to_dict(row),
        [repository.step_to_dict(step) for step in steps],
    )
    return {
        "execution_id": execution_id,
        "format": "markdown",
        "markdown": markdown,
        "copy_markdown": copy_markdown,
        "text": build_report_text(copy_markdown),
        "editable": True,
        "presentation": presentation,
        "procedure": spec.to_dict() if spec else None,
    }


@router.post("/{execution_id}/report/export")
def export_report(
    execution_id: str,
    payload: ExportReportRequest,
    db: Database = Depends(get_database),
    _csrf: None = CSRFDependency,
) -> PlainTextResponse:
    """Exporta o relatório, opcionalmente com o texto editado pelo operador.

    Quando ``edited_text`` é enviado, o conteúdo editado pelo técnico é o que
    será exportado — o relatório original permanece intacto no histórico.
    """
    with db.session() as session:
        row = repository.get_execution(session, execution_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execução não encontrada.",
            )
        steps = repository.get_steps(session, execution_id)

    try:
        spec = registry.get_spec(row.procedure_id)
    except ProcedureNotFoundError:
        spec = None

    markdown = build_report_markdown(row, steps, spec)
    if payload.edited_text:
        content = payload.edited_text
    elif payload.format == "text":
        content = build_report_text(
            build_report_markdown(row, steps, spec, include_dev_details=False)
        )
    else:
        content = markdown

    extension = "txt" if payload.format == "text" else "md"
    filename = f"deskguard-{execution_id[:8]}.{extension}"
    media_type = (
        "text/plain; charset=utf-8"
        if payload.format == "text"
        else "text/markdown; charset=utf-8"
    )

    with db.session() as session:
        repository.record_audit(
            session,
            action=AuditAction.REPORT_EXPORTED,
            target=f"{row.procedure_id}#{execution_id}",
            outcome="ok",
            mode=row.mode,
            execution_id=execution_id,
            details={"format": payload.format, "edited": bool(payload.edited_text)},
        )

    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
