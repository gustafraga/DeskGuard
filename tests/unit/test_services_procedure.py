"""Testes do procedimento ``services.status`` e da interpretação de serviços.

O objetivo é validar a *interpretação* do estado dos serviços — a parte que
decide se algo é falha confirmada, aviso, estado esperado ou inconclusividade
— sem depender do estado real do computador do operador.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from deskguard.collectors.base import ProbeContext
from deskguard.collectors.powershell import PowerShellOutcome
from deskguard.collectors.service_status import (
    SERVICE_PROFILES,
    classify_service,
    classify_startup,
    normalize_service_name,
    profile_for,
)
from deskguard.domain.enums import CheckStatus, ExecutionMode
from deskguard.procedures import services_status

# --------------------------------------------------------------------------
# Infraestrutura de teste
# --------------------------------------------------------------------------


class _FakeRunner:
    """Substitui o executor PowerShell por um resultado pré-definido."""

    payload: dict[str, Any] = {}
    ok = True
    stderr = ""
    returncode = 0
    duracao_ms = 12
    recebido: dict[str, Any] = {}

    def run_script(self, script, payload=None, *, timeout_s=20.0):  # noqa: ANN001
        _FakeRunner.recebido = dict(payload or {})
        return PowerShellOutcome(
            ok=self.ok,
            payload=self.payload,
            stdout="",
            stderr=self.stderr,
            duration_ms=self.duracao_ms,
            returncode=self.returncode,
        )


def _ctx(params: dict[str, Any] | None = None):
    return ProbeContext(
        execution_id="exec-teste",
        mode=ExecutionMode.LIVE,
        timeout_s=10.0,
        params=params or {},
        shared={},
    )


@pytest.fixture(autouse=True)
def _fake_runner(monkeypatch: pytest.MonkeyPatch):
    _FakeRunner.payload = {}
    _FakeRunner.ok = True
    _FakeRunner.stderr = ""
    _FakeRunner.returncode = 0
    _FakeRunner.recebido = {}
    monkeypatch.setattr(services_status, "PowerShellRunner", _FakeRunner)
    return _FakeRunner


def _servico(
    nome: str = "Spooler",
    status: str = "Running",
    start_type: str = "Automatic",
    depends_on: list[str] | None = None,
    dependents: list[str] | None = None,
    found: bool = True,
) -> dict[str, Any]:
    return {
        "name": nome,
        "display_name": nome,
        "status": status,
        "start_type": start_type,
        "path": "C:\\Windows\\System32\\svchost.exe",
        "exit_code": 0,
        "service_type": "Share Process",
        "depends_on": depends_on or [],
        "dependents": dependents or [],
        "found": found,
        "error": "",
    }


def _payload(servicos: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    lista = servicos if servicos is not None else [_servico()]
    return {
        "services.inventory": {
            "available": True,
            "count": len(lista),
            "services": lista,
            "error": "",
            "module_error": "",
        },
        "services.dependencies": {
            "available": True,
            "count": len(lista),
            "dependencies": [
                {
                    "name": servico["name"],
                    "depends_on": servico["depends_on"],
                    "dependents": servico["dependents"],
                }
                for servico in lista
            ],
            "error": "",
        },
    }


def _por_id(resultados) -> dict[str, Any]:
    return {resultado.check_id: resultado for resultado in resultados}


def _executar() -> dict[str, Any]:
    return _por_id(services_status.ServicesStatusProcedure().run(_ctx()))


# --------------------------------------------------------------------------
# services.inventory
# --------------------------------------------------------------------------


def test_servicos_saudaveis_aprovam_todas_as_etapas() -> None:
    _FakeRunner.payload = _payload(
        [
            _servico("Spooler"),
            _servico("Dnscache"),
            _servico("DHCP"),
            _servico("WlanSvc"),
            _servico("wuauserv", start_type="Manual"),
        ]
    )

    resultados = _executar()
    assert set(resultados) == {
        "services.inventory",
        "services.startup",
        "services.dependencies",
    }
    assert all(r.status is CheckStatus.PASS for r in resultados.values())


def test_spooler_parado_com_inicio_automatico_e_falha_confirmada() -> None:
    _FakeRunner.payload = _payload([_servico("Spooler", status="Stopped")])

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.FAIL
    assert resultados["services.inventory"].severity.value == "high"
    assert "Spooler" in resultados["services.inventory"].message


def test_servico_parado_com_inicio_manual_gera_apenas_aviso() -> None:
    _FakeRunner.payload = _payload(
        [_servico("DHCP", status="Stopped", start_type="Manual")]
    )

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.WARN


def test_windows_update_parado_e_estado_esperado() -> None:
    """Serviço de disparo por evento parado não é falha."""
    _FakeRunner.payload = _payload(
        [_servico("wuauserv", status="Stopped", start_type="Manual")]
    )

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.PASS


def test_windows_update_desativado_gera_aviso_e_nao_falha() -> None:
    _FakeRunner.payload = _payload(
        [_servico("wuauserv", status="Stopped", start_type="Disabled")]
    )

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.WARN
    assert resultados["services.startup"].status is CheckStatus.WARN


def test_spooler_desativado_e_falha_confirmada() -> None:
    _FakeRunner.payload = _payload(
        [_servico("Spooler", status="Stopped", start_type="Disabled")]
    )

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.FAIL
    assert resultados["services.startup"].status is CheckStatus.FAIL


def test_servico_inexistente_nao_aplica_e_nao_falha() -> None:
    _FakeRunner.payload = _payload(
        [
            _servico("Spooler"),
            _servico("WlanSvc", found=False),
        ]
    )

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.PASS
    aplicaveis = resultados["services.inventory"].evidence["not_applicable"]
    assert aplicaveis == ["WlanSvc"]


def test_estado_desconhecido_e_inconclusivo() -> None:
    _FakeRunner.payload = _payload([_servico("Spooler", status="Unknown")])

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.INCONCLUSIVE


def test_estado_transitorio_e_inconclusivo() -> None:
    _FakeRunner.payload = _payload([_servico("Spooler", status="Pending")])

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.INCONCLUSIVE


def test_servico_pausado_e_falha_confirmada_quando_critico() -> None:
    _FakeRunner.payload = _payload([_servico("Spooler", status="Paused")])

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.FAIL


def test_servico_pausado_gera_aviso_quando_de_baixa_criticidade() -> None:
    _FakeRunner.payload = _payload(
        [_servico("wuauserv", status="Paused", start_type="Manual")]
    )

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.WARN


def test_falha_do_script_torna_todas_as_etapas_inconclusivas() -> None:
    _FakeRunner.ok = False
    _FakeRunner.stderr = "erro simulado"
    _FakeRunner.returncode = 1

    resultados = _executar()
    assert len(resultados) == 3
    assert all(r.status is CheckStatus.INCONCLUSIVE for r in resultados.values())


def test_secao_ausente_e_inconclusiva() -> None:
    _FakeRunner.payload = {"services.inventory": {"services": [_servico()]}}

    resultados = _executar()
    assert resultados["services.dependencies"].status is CheckStatus.INCONCLUSIVE
    assert resultados["services.dependencies"].error_code == "MISSING_SECTION"


def test_inventario_indisponivel_e_inconclusivo() -> None:
    _FakeRunner.payload = {
        "services.inventory": {
            "available": False,
            "services": [],
            "error": "acesso negado",
        },
        "services.dependencies": {"available": False, "dependencies": []},
    }

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.INCONCLUSIVE
    assert resultados["services.inventory"].error_code == "SERVICES_UNAVAILABLE"


def test_inventario_vazio_e_inconclusivo() -> None:
    _FakeRunner.payload = _payload([])

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.INCONCLUSIVE
    assert resultados["services.inventory"].error_code == "NO_SERVICES"


# --------------------------------------------------------------------------
# services.startup
# --------------------------------------------------------------------------


def test_tipo_de_inicializacao_divergente_gera_aviso() -> None:
    _FakeRunner.payload = _payload(
        [_servico("Spooler", start_type="Manual")]
    )

    resultados = _executar()
    assert resultados["services.startup"].status is CheckStatus.WARN
    assert "Automático" in resultados["services.startup"].message or (
        "Automatic" in resultados["services.startup"].message
    )


def test_tipo_de_inicializacao_desconhecido_e_inconclusivo() -> None:
    _FakeRunner.payload = _payload(
        [_servico("Spooler", start_type="Unknown")]
    )

    resultados = _executar()
    assert resultados["services.startup"].status is CheckStatus.INCONCLUSIVE


def test_servico_em_execucao_mas_desativado_gera_aviso() -> None:
    """Serviço em execução com inicialização desativada não volta após o boot."""
    _FakeRunner.payload = _payload(
        [_servico("Spooler", status="Running", start_type="Disabled")]
    )

    resultados = _executar()
    assert resultados["services.inventory"].status is CheckStatus.WARN
    assert resultados["services.startup"].status is CheckStatus.FAIL


# --------------------------------------------------------------------------
# services.dependencies
# --------------------------------------------------------------------------


def test_dependencia_parada_quebra_o_servico_dependente() -> None:
    _FakeRunner.payload = _payload(
        [
            _servico("Spooler", status="Stopped", dependents=["Fax"]),
            _servico("Dnscache", status="Running", depends_on=["Spooler"]),
        ]
    )

    resultados = _executar()
    assert resultados["services.dependencies"].status is CheckStatus.FAIL
    assert "parado" in resultados["services.dependencies"].message


def test_servico_parado_com_dependentes_monitorados_gera_aviso() -> None:
    _FakeRunner.payload = _payload(
        [
            _servico("Spooler", status="Stopped", dependents=["DnsCache"]),
            _servico("DnsCache", status="Running", depends_on=[]),
        ]
    )

    resultados = _executar()
    assert resultados["services.dependencies"].status is CheckStatus.WARN


def test_dependencias_saudaveis_aprovam() -> None:
    _FakeRunner.payload = _payload(
        [
            _servico("Spooler", status="Running", depends_on=["RPCSS"]),
            _servico("RpcSs", status="Running"),
        ]
    )

    resultados = _executar()
    assert resultados["services.dependencies"].status is CheckStatus.PASS


def test_nome_de_servico_e_normalizado_para_comparacao() -> None:
    assert normalize_service_name("RPCSS") == "rpcss"
    assert normalize_service_name("RPCSS,http") == "rpcss"
    assert normalize_service_name("  RpcSs ") == "rpcss"
    assert normalize_service_name("") == ""


def test_dependencia_com_alias_do_windows_e_reconhecida() -> None:
    _FakeRunner.payload = _payload(
        [
            _servico("Spooler", status="Stopped", dependents=["Fax"]),
            _servico("RpcSs", status="Stopped"),
            _servico("DcomLaunch", status="Running", depends_on=["RPCSS,http"]),
        ]
    )

    resultados = _executar()
    assert resultados["services.dependencies"].status is CheckStatus.FAIL


# --------------------------------------------------------------------------
# Módulo de interpretação
# --------------------------------------------------------------------------


def test_perfil_por_servico_e_encontrado_sem_distincao_de_maiusculas() -> None:
    assert profile_for("spooler") is SERVICE_PROFILES["spooler"]
    assert profile_for("SPOOLER") is SERVICE_PROFILES["spooler"]
    assert profile_for("servico-inexistente") is None


def test_servico_sem_perfil_parado_com_inicio_automatico_e_falha_baixa() -> None:
    """Sem perfil não se conhece a criticidade, mas o desvio é confirmado."""
    estado = classify_service(_servico("ServicoDesconhecido", status="Stopped"))

    assert estado.status is CheckStatus.FAIL
    assert estado.severity.value == "low"


def test_servico_sem_perfil_em_execucao_aprovam() -> None:
    estado = classify_service(_servico("ServicoDesconhecido"))

    assert estado.status is CheckStatus.PASS


def test_classificacao_de_inicializacao_aceita_padrao_conhecido() -> None:
    estado = classify_startup(_servico("wuauserv", start_type="Manual"))

    assert estado.status is CheckStatus.PASS


def test_classificacao_de_inicializacao_rejeita_padrao_divergente() -> None:
    estado = classify_startup(_servico("wuauserv", start_type="Automatic"))

    assert estado.status is CheckStatus.WARN


# --------------------------------------------------------------------------
# Procedimento e catálogo
# --------------------------------------------------------------------------


def test_parametro_include_supporting_e_encaminhado_ao_script() -> None:
    _FakeRunner.payload = _payload([_servico()])

    services_status.ServicesStatusProcedure().run(
        _ctx({"include_supporting": False})
    )

    assert _FakeRunner.recebido == {"include_supporting": False}


def test_procedimento_e_registrado_como_somente_leitura() -> None:
    from deskguard.catalog import registry

    registry.load_builtin_procedures()
    spec = registry.get_spec("services.status")

    assert spec.read_only is True
    assert spec.category == "Serviços"
    assert spec.privilege.value == "user"
    assert spec.steps


def test_modo_demonstracao_marca_os_resultados_como_simulados() -> None:
    procedimento = services_status.ServicesStatusProcedure().for_mode(ExecutionMode.DEMO)

    resultados = procedimento.run(_ctx())
    assert resultados
    assert all(r.simulated is True for r in resultados)
    assert all(r.evidence.get("simulated") is True for r in resultados)


def test_script_do_procedimento_existe_e_e_ascii_puro() -> None:
    from deskguard.collectors.powershell import script_path

    conteudo = script_path("services_status.ps1").read_bytes()
    assert all(byte < 128 for byte in conteudo), "services_status.ps1 contem bytes nao-ASCII"


def test_script_nao_executa_comandos_que_alteram_o_sistema() -> None:
    from deskguard.collectors.powershell import script_path

    proibidos = (
        "Start-Service",
        "Stop-Service",
        "Restart-Service",
        "Set-Service",
        "sc.exe config",
        "sc.exe start",
        "sc.exe stop",
        "New-Service",
        "Remove-Service",
        "Set-NetIPAddress",
        "New-NetFirewallRule",
        "Set-ItemProperty",
    )
    texto = _codigo_execucao(script_path("services_status.ps1").read_text(encoding="utf-8"))
    for comando in proibidos:
        assert comando not in texto, f"services_status.ps1 contem o comando {comando}"


def _codigo_execucao(texto: str) -> str:
    """Remove os comentários do script, deixando apenas o código executado."""
    import re

    sem_bloco = re.sub(r"<#.*?#>", "", texto, flags=re.DOTALL)
    linhas = [
        linha for linha in sem_bloco.splitlines() if not linha.strip().startswith("#")
    ]
    return "\n".join(linhas)


def test_script_le_o_payload_do_ambiente_e_nao_a_linha_de_comando() -> None:
    from deskguard.collectors.powershell import script_path

    texto = script_path("services_status.ps1").read_text(encoding="utf-8")
    assert "DESKGUARD_PAYLOAD_PATH" in texto
    assert "Get-Service" in texto
    assert Path("src/deskguard/collectors/scripts/services_status.ps1").exists()
