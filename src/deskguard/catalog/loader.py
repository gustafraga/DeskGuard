"""Carregamento automático dos módulos de procedimento do catálogo."""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from deskguard.catalog import registry

_LOADED = False


def _procedure_package() -> ModuleType:
    return importlib.import_module("deskguard.procedures")


def load_builtin_procedures(force: bool = False) -> None:
    """Importa todos os módulos de `deskguard.procedures`.

    O uso de `pkgutil` significa que um novo procedimento passa a existir no
    catálogo apenas por ser criado como módulo no pacote, sem edição manual
    de listas centralizadas.
    """
    global _LOADED
    if _LOADED and not force:
        return
    package = _procedure_package()
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name.startswith("_"):
            continue
        importlib.import_module(f"{package.__name__}.{module_info.name}")
    _LOADED = True


def registered_count() -> int:
    load_builtin_procedures()
    return len(registry.list_specs())
