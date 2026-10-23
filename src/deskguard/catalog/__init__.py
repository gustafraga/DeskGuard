"""Infraestrutura do catálogo de procedimentos."""

from deskguard.catalog.loader import load_builtin_procedures, registered_count
from deskguard.catalog.registry import (
    categories,
    get_factory,
    get_spec,
    is_registered,
    list_specs,
    register,
)

__all__ = [
    "categories",
    "get_factory",
    "get_spec",
    "is_registered",
    "list_specs",
    "load_builtin_procedures",
    "register",
    "registered_count",
]
