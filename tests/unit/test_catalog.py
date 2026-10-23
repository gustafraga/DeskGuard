"""Testes do catálogo de procedimentos."""

from __future__ import annotations

import pytest

from deskguard.catalog import registry
from deskguard.domain.enums import Capability
from deskguard.errors import ProcedureNotFoundError


def test_catalogo_carrega_procedimento_padrao() -> None:
    registry.load_builtin_procedures()
    spec = registry.get_spec("system.overview")
    assert spec.title == "Visão geral do sistema"
    assert spec.capability is Capability.READ_ONLY
    assert spec.read_only is True
    assert spec.requires_approval is False
    assert len(spec.steps) == 6


def test_catalogo_descreve_parametros_e_etapas() -> None:
    registry.load_builtin_procedures()
    spec = registry.get_spec("system.overview")
    parametros = {param.name: param for param in spec.params}
    assert "include_account" in parametros
    assert parametros["include_account"].default is False
    assert {step.id for step in spec.steps} >= {
        "os.version",
        "system.identity",
        "system.uptime",
        "system.hardware",
        "system.runtime",
        "system.storage",
    }


def test_procedimento_inexistente_gera_erro_explicito() -> None:
    with pytest.raises(ProcedureNotFoundError):
        registry.get_spec("nao.existe")


def test_categorias_agrupam_procedimentos() -> None:
    registry.load_builtin_procedures()
    categorias = registry.categories()
    assert "Sistema" in categorias
    assert any(spec.id == "system.overview" for spec in categorias["Sistema"])


def test_registro_remove_procedimento_de_teste() -> None:
    registry.load_builtin_procedures()
    assert registry.is_registered("test.fake.readonly")
    registry.unregister("test.fake.readonly")
    assert not registry.is_registered("test.fake.readonly")
    # Restaura o procedimento para os demais testes da sessão.
    registry.load_builtin_procedures(force=True)
    import tests.fakes  # noqa: F401

    tests.fakes.FakeReadOnlyProcedure  # noqa: B018 - garante reimportação
