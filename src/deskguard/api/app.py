"""Aplicação FastAPI local do DeskGuard.

A API escuta apenas em 127.0.0.1, exige um token anti-CSRF nas operações que
alteram estado e recusa requisições originadas de hosts não locais. Não há
nenhum endpoint de execução de comandos: as únicas ações possíveis são as
definidas no catálogo de procedimentos.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from deskguard.api import routes
from deskguard.api.middleware import HostValidationMiddleware, SecurityHeadersMiddleware
from deskguard.catalog import registry
from deskguard.config import Settings
from deskguard.errors import (
    CapabilityDeniedError,
    CollectorError,
    InvalidParametersError,
    ProcedureNotFoundError,
    SecurityError,
)
from deskguard.services.execution import ExecutionService
from deskguard.storage.database import Database
from deskguard.version import __version__

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
TEMPLATES_DIR = WEB_ROOT / "templates"
STATIC_DIR = WEB_ROOT / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria e configura a aplicação do DeskGuard."""
    effective_settings = settings or Settings.from_env()
    effective_settings.ensure_directories()

    registry.load_builtin_procedures()

    database = Database(effective_settings.database_path)
    database.create_all()
    execution_service = ExecutionService(database, effective_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        execution_service.shutdown()
        database.dispose()

    app = FastAPI(
        title="DeskGuard",
        version=__version__,
        description=(
            "Plataforma local de automação de Service Desk e diagnóstico de "
            "endpoints Windows."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.state.settings = effective_settings
    app.state.db = database
    app.state.execution_service = execution_service
    app.state.csrf_token = secrets.token_urlsafe(32)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(HostValidationMiddleware)

    app.include_router(routes.system.router, prefix="/api")
    app.include_router(routes.catalog.router, prefix="/api")
    app.include_router(routes.executions.router, prefix="/api")
    app.include_router(routes.reports.router, prefix="/api")
    app.include_router(routes.audit.router, prefix="/api")
    app.include_router(routes.remediation.router, prefix="/api")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index(request: Request) -> Response:
        """Interface web do DeskGuard."""
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "csrf_token": app.state.csrf_token,
                "version": __version__,
                "mode": str(effective_settings.mode),
            },
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.exception_handler(ProcedureNotFoundError)
    def _procedure_not_found(_request: Request, exc: ProcedureNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidParametersError)
    def _invalid_parameters(_request: Request, exc: InvalidParametersError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(CapabilityDeniedError)
    def _capability_denied(_request: Request, exc: CapabilityDeniedError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(CollectorError)
    def _collector_error(_request: Request, exc: CollectorError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(SecurityError)
    def _security_error(_request: Request, exc: SecurityError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    return app


app = create_app()
