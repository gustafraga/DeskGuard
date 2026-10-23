"""Testes da validação de parâmetros e da política de capacidade."""

from __future__ import annotations

import pytest

from deskguard.domain.enums import Capability
from deskguard.domain.spec import ParamSpec, ProcedureSpec
from deskguard.errors import CapabilityDeniedError, InvalidParametersError
from deskguard.security.allowlist import (
    MAX_TARGETS,
    AllowedTarget,
    TargetAllowlist,
)
from deskguard.security.capabilities import CapabilityPolicy
from deskguard.security.validation import validate_params


def _spec(params: tuple[ParamSpec, ...] = (), capability: Capability = Capability.READ_ONLY) -> ProcedureSpec:
    return ProcedureSpec(
        id="test.spec",
        title="Spec de teste",
        category="Testes",
        summary="",
        description="",
        capability=capability,
        params=params,
    )


def test_parametro_desconhecido_e_rejeitado() -> None:
    spec = _spec()
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"inesperado": 1})


def test_parametro_obrigatorio_ausente_e_rejeitado() -> None:
    spec = _spec((ParamSpec(name="obrigatorio", label="X", required=True),))
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {})


def test_valor_padrao_e_aplicado() -> None:
    spec = _spec((ParamSpec(name="fator", label="Fator", type="integer", default=7),))
    assert validate_params(spec, {}) == {"fator": 7}


def test_inteiro_fora_do_intervalo_e_rejeitado() -> None:
    spec = _spec(
        (ParamSpec(name="porta", label="Porta", type="integer", min_value=1, max_value=65535),)
    )
    validate_params(spec, {"porta": 8080})
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"porta": 70000})
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"porta": "texto"})


def test_booleano_aceita_varias_representacoes() -> None:
    spec = _spec((ParamSpec(name="flag", label="Flag", type="boolean", default=False),))
    assert validate_params(spec, {"flag": True})["flag"] is True
    assert validate_params(spec, {"flag": "sim"})["flag"] is True
    assert validate_params(spec, {"flag": "0"})["flag"] is False
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"flag": "talvez"})


def test_enum_restringe_as_opcoes() -> None:
    spec = _spec((ParamSpec(name="modo", label="Modo", type="enum", choices=("a", "b")),))
    assert validate_params(spec, {"modo": "a"})["modo"] == "a"
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"modo": "c"})


def test_padrao_de_hostname_rejeita_caracteres_invalidos() -> None:
    spec = _spec(
        (
            ParamSpec(
                name="host",
                label="Host",
                pattern=r"[A-Za-z0-9._-]{1,253}",
            ),
        )
    )
    validate_params(spec, {"host": "servidor.corp.local"})
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"host": "host; DROP TABLE"})


def test_stringo_acima_do_limite_e_rejeitado() -> None:
    spec = _spec((ParamSpec(name="texto", label="Texto", max_length=10),))
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"texto": "x" * 50})


def _spec_host_list():
    return _spec(
        (
            ParamSpec(
                name="targets",
                label="Destinos",
                type="host_list",
                default=(),
            ),
        )
    )


def _allowlist(*hosts: str) -> TargetAllowlist:
    return TargetAllowlist(
        targets=tuple(AllowedTarget(host=host) for host in hosts),
        available=True,
    )


def test_lista_de_destinos_aceita_apenas_autorizados() -> None:
    spec = _spec_host_list()
    allowlist = _allowlist("intranet.corp.local", "10.0.0.5")

    resultado = validate_params(
        spec, {"targets": ["intranet.corp.local", "10.0.0.5"]}, allowlist=allowlist
    )
    assert resultado["targets"] == ["intranet.corp.local", "10.0.0.5"]


def test_destino_nao_autorizado_e_rejeitado() -> None:
    spec = _spec_host_list()
    with pytest.raises(InvalidParametersError) as erro:
        validate_params(
            spec, {"targets": ["8.8.8.8"]}, allowlist=_allowlist("intranet.corp.local")
        )
    assert "autorizados" in str(erro.value).lower()


def test_lista_vazia_de_autorizados_recusa_tudo() -> None:
    spec = _spec_host_list()
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"targets": ["intranet.corp.local"]}, allowlist=_allowlist())


def test_sintaxe_invalida_de_destino_e_rejeitada() -> None:
    spec = _spec_host_list()
    for host in ("host com espaco", "*.corp.local", "10.0.0.0/24", "http://servidor"):
        with pytest.raises(InvalidParametersError):
            validate_params(spec, {"targets": [host]}, allowlist=_allowlist("a.local"))


def test_lista_de_destinos_aceita_texto_separado() -> None:
    spec = _spec_host_list()
    allowlist = _allowlist("a.local", "b.local")

    resultado = validate_params(spec, {"targets": "a.local, b.local"}, allowlist=allowlist)
    assert resultado["targets"] == ["a.local", "b.local"]


def test_quantidade_excessiva_de_destinos_e_rejeitada() -> None:
    spec = _spec_host_list()
    hosts = [f"servidor{indice}.local" for indice in range(MAX_TARGETS + 1)]
    allowlist = _allowlist(*hosts)
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"targets": hosts}, allowlist=allowlist)


def test_parametro_de_lista_desconhecido_e_rejeitado() -> None:
    spec = _spec_host_list()
    with pytest.raises(InvalidParametersError):
        validate_params(spec, {"destinos": ["a.local"]}, allowlist=_allowlist("a.local"))


def test_procedimento_de_leitura_nao_exige_aprovacao() -> None:
    decision = CapabilityPolicy.evaluate(_spec(), approved=False)
    assert decision.allowed is True
    assert decision.requires_approval is False


def test_procedimento_modificante_exige_aprovacao() -> None:
    spec = _spec(capability=Capability.MODIFYING)
    denied = CapabilityPolicy.evaluate(spec, approved=False)
    assert denied.allowed is False
    assert denied.requires_approval is True

    with pytest.raises(CapabilityDeniedError):
        CapabilityPolicy.authorize(spec, approved=False)

    allowed = CapabilityPolicy.authorize(spec, approved=True)
    assert allowed.allowed is True
    assert allowed.requires_approval is True
