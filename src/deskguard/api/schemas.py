"""Modelos de entrada e saída da API local."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RunExecutionRequest(BaseModel):
    """Solicitação de execução de um procedimento."""

    model_config = ConfigDict(extra="forbid")

    procedure_id: str = Field(min_length=3, max_length=80)
    params: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["live", "demo"] = "live"
    approved: bool = False


class ExportReportRequest(BaseModel):
    """Solicitação de exportação do relatório de uma execução."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["markdown", "text"] = "markdown"
    edited_text: str | None = Field(default=None, max_length=200_000)


class HealthResponse(BaseModel):
    status: str
    version: str
    mode: str
    procedures: int
    database: str
    python: str
    platform: str
    is_admin: bool | None
    powershell_available: bool


class ProcedureSummary(BaseModel):
    id: str
    title: str
    category: str
    summary: str
    capability: str
    read_only: bool
    privilege: str
    version: str
    tags: list[str]
    source_mode: str


class ProcedureListResponse(BaseModel):
    count: int
    categories: list[dict[str, Any]]
    procedures: list[ProcedureSummary]


class ExecutionAcceptedResponse(BaseModel):
    execution_id: str
    status: str
    procedure_id: str
