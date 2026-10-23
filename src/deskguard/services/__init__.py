"""Camada de serviços: regras de negócio da plataforma."""

from deskguard.services.execution import ExecutionOutcome, ExecutionService
from deskguard.services.report import build_report_markdown, build_report_text

__all__ = [
    "ExecutionOutcome",
    "ExecutionService",
    "build_report_markdown",
    "build_report_text",
]
