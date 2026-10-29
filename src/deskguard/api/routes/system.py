"""Rotas de sistema: saúde, painel e configurações."""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Depends

from deskguard.api.deps import get_database, get_settings
from deskguard.catalog import registry
from deskguard.collectors.powershell import PowerShellRunner
from deskguard.collectors.python_stdlib import is_admin
from deskguard.config import Settings
from deskguard.desktop import desktop_availability
from deskguard.domain.enums import AuditAction
from deskguard.procedures.ad_self_status import (
    collect_self_status_summary,
    inconclusive_self_status_summary,
)
from deskguard.security.allowlist import allowlist_path_for, load_allowlist
from deskguard.storage import repository
from deskguard.storage.database import Database
from deskguard.version import __version__

router = APIRouter(tags=["sistema"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    """Estado da ferramenta, usado para diagnóstico da própria instalação."""
    registry.load_builtin_procedures()
    return {
        "status": "ok",
        "application": "deskguard",
        "version": __version__,
        "mode": str(settings.mode),
        "procedures": len(registry.list_specs()),
        "database": str(settings.database_path),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "is_admin": is_admin(),
        "powershell_available": PowerShellRunner().available,
    }


@router.get("/dashboard")
def dashboard(db: Database = Depends(get_database)) -> dict:
    """Indicadores calculados a partir das execuções realmente registradas."""
    with db.session() as session:
        stats = repository.dashboard_stats(session)
    stats["generated_at"] = repository.utcnow().isoformat()
    return stats


@router.get("/ad/self-status")
def ad_self_status(settings: Settings = Depends(get_settings)) -> dict:
    """Conta do usuário logado e confiança do domínio para o Dashboard.

    A consulta usa o contexto de segurança do próprio técnico: nenhuma
    credencial adicional é recebida pela API nem repassada ao PowerShell.
    O painel tem prioridade sobre a coleta completa: o tempo é curto e
    qualquer falha vira um resultado inconclusivo, nunca um erro 500.
    """
    try:
        return collect_self_status_summary(timeout_s=settings.request_timeout_s)
    except Exception as exc:  # noqa: BLE001 - o Dashboard não pode travar
        return inconclusive_self_status_summary(
            detail=f"{type(exc).__name__}: {exc}"
        )


@router.get("/settings")
def settings_view(settings: Settings = Depends(get_settings)) -> dict:
    """Configuração efetiva e informações de privilégio do processo."""
    registry.load_builtin_procedures()
    return {
        "settings": settings.to_dict(),
        "privilege": {
            "is_admin": is_admin(),
            "description": (
                "Processo com elevação administrativa: coletas que exigem "
                "privilégio elevado estão disponíveis."
                if is_admin()
                else "Processo sem elevação: coletas que exigem privilégio elevado "
                "serão marcadas como inconclusivas."
            ),
        },
        "catalog": {
            "count": len(registry.list_specs()),
            "categories": sorted({spec.category for spec in registry.list_specs()}),
        },
        "allowlist": load_allowlist(allowlist_path_for(settings.data_dir)).to_dict(),
        "desktop": desktop_availability(),
        "tool_version": __version__,
    }


@router.post("/settings/audit-view")
def register_settings_view(db: Database = Depends(get_database)) -> dict:
    """Registra a consulta às configurações na trilha de auditoria."""
    with db.session() as session:
        repository.record_audit(
            session,
            action=AuditAction.SETTINGS_VIEWED,
            target="settings",
            outcome="ok",
        )
    return {"registered": True}
