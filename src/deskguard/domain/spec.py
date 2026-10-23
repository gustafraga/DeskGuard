"""Metadados que descrevem um procedimento do catálogo.

A especificação é declarada pelo autor do procedimento e é a única fonte de
verdade sobre o que a ferramenta faz, exige e pode alterar. A interface, a
API e o relatório consomem sempre essa descrição, nunca valores duplicados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from deskguard.domain.enums import Capability, ExecutionMode, PrivilegeLevel


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """Descrição de um parâmetro aceito por um procedimento."""

    name: str
    label: str
    type: Literal["string", "integer", "boolean", "enum", "host_list"] = "string"
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    help_text: str = ""
    min_value: int | None = None
    max_value: int | None = None
    pattern: str | None = None
    max_length: int = 512

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "choices": list(self.choices),
            "help_text": self.help_text,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "pattern": self.pattern,
            "max_length": self.max_length,
        }


@dataclass(frozen=True, slots=True)
class ProcedureSpec:
    """Descrição completa de um procedimento do catálogo."""

    id: str
    title: str
    category: str
    summary: str
    description: str
    capability: Capability = Capability.READ_ONLY
    privilege: PrivilegeLevel = PrivilegeLevel.USER
    risk_notes: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    expected_outcomes: tuple[str, ...] = ()
    params: tuple[ParamSpec, ...] = ()
    steps: tuple[StepSpec, ...] = ()
    version: str = "1.0.0"
    tags: tuple[str, ...] = ()
    source_mode: ExecutionMode = ExecutionMode.LIVE

    @property
    def read_only(self) -> bool:
        return self.capability is Capability.READ_ONLY

    @property
    def requires_approval(self) -> bool:
        return self.capability is Capability.MODIFYING

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "summary": self.summary,
            "description": self.description,
            "capability": str(self.capability),
            "read_only": self.read_only,
            "privilege": str(self.privilege),
            "risk_notes": list(self.risk_notes),
            "prerequisites": list(self.prerequisites),
            "expected_outcomes": list(self.expected_outcomes),
            "params": [param.to_dict() for param in self.params],
            "steps": [
                {
                    "id": step.id,
                    "title": step.title,
                    "description": step.description,
                    "depends_on": list(step.depends_on),
                }
                for step in self.steps
            ],
            "version": self.version,
            "tags": list(self.tags),
            "source_mode": str(self.source_mode),
        }


@dataclass(frozen=True, slots=True)
class StepSpec:
    """Descrição de uma etapa de verificação dentro de um procedimento."""

    id: str
    title: str
    description: str
    depends_on: tuple[str, ...] = field(default=())
