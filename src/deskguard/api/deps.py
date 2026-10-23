"""Dependências compartilhadas das rotas da API."""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Request, status

from deskguard.config import Settings
from deskguard.services.execution import ExecutionService
from deskguard.storage.database import Database


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_execution_service(request: Request) -> ExecutionService:
    return request.app.state.execution_service


def require_csrf(
    request: Request,
    x_deskguard_csrf: str | None = Header(default=None, alias="X-DeskGuard-CSRF"),
) -> None:
    """Exige o token anti-CSRF em operações que alteram estado.

    O token é gerado a cada inicialização do servidor e entregue apenas à
    página servida pela própria aplicação, de modo que outra origem não
    consiga lê-lo.
    """
    expected = getattr(request.app.state, "csrf_token", "")
    if not x_deskguard_csrf or not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token anti-CSRF ausente. Recarregue a página do DeskGuard.",
        )
    if not hmac.compare_digest(x_deskguard_csrf, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token anti-CSRF inválido. Recarregue a página do DeskGuard.",
        )


CSRFDependency = Depends(require_csrf)
