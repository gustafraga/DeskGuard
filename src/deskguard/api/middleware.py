"""Middlewares de segurança da API local."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1", "0.0.0.0"}

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
}


class HostValidationMiddleware(BaseHTTPMiddleware):
    """Recusa requisições cujo cabeçalho Host não seja local.

    Sem essa checagem, um site malicioso poderia resolve o nome `localhost`
    para o endereço da interface local e falar com a API por meio de DNS
    rebinding, contornando a proteção de origem do navegador.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = request.headers.get("host", "")
        hostname = host.split(":")[0].strip().lower()
        if hostname not in _ALLOWED_HOSTS:
            return Response(
                content='{"detail":"Host não autorizado. A API do DeskGuard aceita '
                'somente requisições locais (localhost/127.0.0.1)."}',
                status_code=403,
                media_type="application/json",
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adiciona cabeçalhos de segurança a todas as respostas."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        response.headers.setdefault("Cache-Control", "no-store")
        return response
