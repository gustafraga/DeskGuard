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
