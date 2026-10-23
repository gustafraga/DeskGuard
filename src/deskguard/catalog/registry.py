"""Registro central de procedimentos do catálogo.

O registro é populado por decorador no momento do import dos módulos de
procedimento. Isso evita tabelas manuais que costumam divergir do código.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from deskguard.domain.spec import ProcedureSpec
from deskguard.errors import ProcedureNotFoundError

if TYPE_CHECKING:  # pragma: no cover - apenas para tipagem
    from deskguard.procedures.base import Procedure


@dataclass(frozen=True, slots=True)
class RegisteredProcedure:
    """Par (descrição, fábrica) de um procedimento disponível no catálogo."""

    spec: ProcedureSpec
    factory: Callable[[], "Procedure"]


_REGISTRY: dict[str, RegisteredProcedure] = {}


def register(cls: type["Procedure"]) -> type["Procedure"]:
    """Decorador que registra uma classe de procedimento no catálogo."""
    spec: ProcedureSpec | None = getattr(cls, "spec", None)
    if spec is None:
        raise TypeError(f"{cls.__name__} não define o atributo 'spec'.")
    if spec.id in _REGISTRY:
        raise ValueError(f"Procedimento duplicado no catálogo: {spec.id}")
    _REGISTRY[spec.id] = RegisteredProcedure(spec=spec, factory=cls)
    return cls


def list_specs() -> tuple[ProcedureSpec, ...]:
    """Retorna todas as especificações, ordenadas por categoria e título."""
    return tuple(
        item.spec
        for item in sorted(
            _REGISTRY.values(), key=lambda item: (item.spec.category, item.spec.title)
        )
    )


def list_registered() -> tuple[RegisteredProcedure, ...]:
    return tuple(
        sorted(_REGISTRY.values(), key=lambda item: (item.spec.category, item.spec.title))
    )


def get_spec(procedure_id: str) -> ProcedureSpec:
    try:
        return _REGISTRY[procedure_id].spec
    except KeyError as exc:
        raise ProcedureNotFoundError(
            f"Procedimento '{procedure_id}' não existe no catálogo."
        ) from exc


def get_factory(procedure_id: str) -> Callable[[], "Procedure"]:
    try:
        return _REGISTRY[procedure_id].factory
    except KeyError as exc:
        raise ProcedureNotFoundError(
            f"Procedimento '{procedure_id}' não existe no catálogo."
        ) from exc


def is_registered(procedure_id: str) -> bool:
    return procedure_id in _REGISTRY


def load_builtin_procedures(force: bool = False) -> None:
    """Carrega os módulos de procedimento (atalho para :mod:`loader`).

    O import é feito de forma tardia porque ``loader`` depende deste módulo:
    a dependência fica invertida apenas no momento da chamada.
    """
    from deskguard.catalog.loader import load_builtin_procedures as _load

    _load(force)


def categories() -> dict[str, list[ProcedureSpec]]:
    """Agrupa as especificações por categoria, com rótulos de exibição."""
    grouped: dict[str, list[ProcedureSpec]] = {}
    for spec in list_specs():
        grouped.setdefault(spec.category, []).append(spec)
    return grouped


def clear() -> None:
    """Limpa o registro. Usado exclusivamente em testes."""
    _REGISTRY.clear()


def unregister(procedure_id: str) -> bool:
    """Remove um procedimento do registro. Usado por testes de integração."""
    return _REGISTRY.pop(procedure_id, None) is not None
