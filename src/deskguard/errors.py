"""Exceções de domínio do DeskGuard."""

from __future__ import annotations


class DeskGuardError(Exception):
    """Erro base da plataforma."""


class ProcedureNotFoundError(DeskGuardError):
    """O identificador informado não existe no catálogo."""


class InvalidParametersError(DeskGuardError):
    """Parâmetros recebidos não atendem à especificação do procedimento."""


class CapabilityDeniedError(DeskGuardError):
    """A operação exigia uma capacidade não concedida ao chamador."""


class CollectorError(DeskGuardError):
    """Falha na camada de coleta de dados do sistema."""


class SecurityError(DeskGuardError):
    """Violação de uma regra de segurança da API local."""
