"""Testes dos procedimentos de rede e de impressoras.

O objetivo é validar a *interpretação* dos dados coletados — a parte que
decide se algo é falha confirmada, aviso ou inconclusividade — sem depender do
estado real do computador do operador.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from deskguard.collectors.base import ProbeContext
from deskguard.collectors.powershell import PowerShellOutcome
from deskguard.domain.enums import CheckStatus, ExecutionMode
from deskguard.procedures import network_connectivity, network_configuration, printers_status

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

    def run_script(self, script, payload=None, *, timeout_s=20.0):  # noqa: ANN001
        return PowerShellOutcome(
            ok=self.ok,
            payload=self.payload,
            stdout="",
            stderr=self.stderr,
            duration_ms=self.duracao_ms,
            returncode=self.returncode,
        )


def _ctx(params: dict[str, Any] | None = None, shared: dict[str, Any] | None = None):
    return ProbeContext(
        execution_id="exec-teste",
        mode=ExecutionMode.LIVE,
        timeout_s=10.0,
        params=params or {},
        shared=shared or {},
    )


@pytest.fixture(autouse=True)
def _fake_runner(monkeypatch: pytest.MonkeyPatch):
    _FakeRunner.payload = {}
    _FakeRunner.ok = True
    _FakeRunner.stderr = ""
    _FakeRunner.returncode = 0
    monkeypatch.setattr(network_configuration, "PowerShellRunner", _FakeRunner)
    monkeypatch.setattr(network_connectivity, "PowerShellRunner", _FakeRunner)
    monkeypatch.setattr(printers_status, "PowerShellRunner", _FakeRunner)
    return _FakeRunner


def _por_id(resultados) -> dict[str, Any]:
    return {resultado.check_id: resultado for resultado in resultados}


# --------------------------------------------------------------------------
# network.configuration
# --------------------------------------------------------------------------


def _config_payload(*, adapters=None, configs=None, routes=None, profiles=None):
    return {
        "network.interfaces": {"count": 1, "adapters": adapters or []},
        "network.ip_configuration": {"count": 1, "configs": configs or []},
        "network.routes": {"count": 1, "default_routes": routes or []},
        "network.profile": {"count": 1, "profiles": profiles or []},
    }


def _adaptador(nome="Ethernet", status="Up"):
    return {
        "name": nome,
        "status": status,
        "media_type": "802.3",
        "link_speed": "100 Mbps",
        "mac_address": "00-11-22-33-44-55",
        "virtual": False,
    }


def _configuracao(ip="10.87.36.130", gateway="10.87.36.254", dns=("10.0.10.6",)):
    return {
        "interface": "Ethernet",
        "has_ipv4": True,
        "addresses": [
            {"family": "IPv4", "address": ip, "prefix": 24, "state": "Preferred"}
        ],
        "gateways": [{"family": "IPv4", "next_hop": gateway}] if gateway else [],
        "dns_servers": list(dns),
    }


def test_configuracao_de_rede_saudavel() -> None:
    _FakeRunner.payload = _config_payload(
        adapters=[_adaptador()],
        configs=[_configuracao()],
        routes=[{"destination": "0.0.0.0/0", "next_hop": "10.87.36.254"}],
        profiles=[{"interface": "Ethernet", "ipv4_state": "Internet"}],
    )

    resultados = _por_id(network_configuration.NetworkConfigurationProcedure().run(_ctx()))
    assert set(resultados) == {
        "network.interfaces",
        "network.ip_configuration",
        "network.routes",
        "network.profile",
    }
    assert all(r.status is CheckStatus.PASS for r in resultados.values())


def test_nenhuma_interface_ativa_e_falha_confirmada() -> None:
    _FakeRunner.payload = _config_payload(adapters=[_adaptador("Wi-Fi", "Disconnected")])

    resultados = _por_id(network_configuration.NetworkConfigurationProcedure().run(_ctx()))
    assert resultados["network.interfaces"].status is CheckStatus.FAIL
    assert resultados["network.interfaces"].severity.value == "high"


def test_interface_desabilitada_gera_aviso() -> None:
    _FakeRunner.payload = _config_payload(
        adapters=[_adaptador(), _adaptador("Wi-Fi", "Disabled")],
        configs=[_configuracao()],
        routes=[{"destination": "0.0.0.0/0"}],
        profiles=[{"interface": "Ethernet", "ipv4_state": "Internet"}],
    )

    resultados = _por_id(network_configuration.NetworkConfigurationProcedure().run(_ctx()))
    assert resultados["network.interfaces"].status is CheckStatus.WARN


def test_sem_ipv4_valido_e_falha_confirmada() -> None:
    _FakeRunner.payload = _config_payload(
        adapters=[_adaptador()],
        configs=[{"interface": "Ethernet", "addresses": [], "gateways": []}],
    )

    resultados = _por_id(network_configuration.NetworkConfigurationProcedure().run(_ctx()))
    assert resultados["network.ip_configuration"].status is CheckStatus.FAIL


def test_sem_gateway_gera_aviso() -> None:
    _FakeRunner.payload = _config_payload(
        adapters=[_adaptador()],
        configs=[_configuracao(gateway=None)],
    )

    resultados = _por_id(network_configuration.NetworkConfigurationProcedure().run(_ctx()))
    assert resultados["network.ip_configuration"].status is CheckStatus.WARN


def test_sem_rota_padrao_gera_aviso() -> None:
    _FakeRunner.payload = _config_payload(
        adapters=[_adaptador()],
        configs=[_configuracao()],
        routes=[],
    )

    resultados = _por_id(network_configuration.NetworkConfigurationProcedure().run(_ctx()))
    assert resultados["network.routes"].status is CheckStatus.WARN


def test_perfil_sem_conectividade_e_falha_confirmada() -> None:
    _FakeRunner.payload = _config_payload(
        adapters=[_adaptador()],
        configs=[_configuracao()],
        profiles=[{"interface": "Ethernet", "ipv4_state": "Disconnected"}],
    )

    resultados = _por_id(network_configuration.NetworkConfigurationProcedure().run(_ctx()))
    assert resultados["network.profile"].status is CheckStatus.FAIL


def test_falha_do_script_torna_todas_as_etapas_inconclusivas() -> None:
    _FakeRunner.ok = False
    _FakeRunner.stderr = "erro simulado"
    _FakeRunner.returncode = 1

    resultados = network_configuration.NetworkConfigurationProcedure().run(_ctx())
    assert len(resultados) == 4
    assert all(r.status is CheckStatus.INCONCLUSIVE for r in resultados)


def test_secao_ausente_e_inconclusiva() -> None:
    _FakeRunner.payload = {"network.interfaces": {"adapters": [_adaptador()]}}

    resultados = _por_id(network_configuration.NetworkConfigurationProcedure().run(_ctx()))
    assert resultados["network.routes"].status is CheckStatus.INCONCLUSIVE
    assert resultados["network.routes"].error_code == "MISSING_SECTION"


# --------------------------------------------------------------------------
# network.connectivity
# --------------------------------------------------------------------------


def _destino(host="intranet.corp.local", resolvido=True, icmp=True, tcp=()):
    return {
        "host": host,
        "source": "allowlist",
        "dns": {
            "resolved": resolvido,
            "addresses": ["10.0.0.20"] if resolvido else [],
            "error": "" if resolvido else "Falha de resolucao DNS.",
        },
        "icmp": {
            "attempted": resolvido,
            "reachable": icmp,
            "status": "Success" if icmp else "TimedOut",
            "rtt_ms": 2 if icmp else None,
            "error": "",
        },
        "tcp": list(tcp),
    }


def test_conectividade_saudavel() -> None:
    _FakeRunner.payload = {
        "targets": [_destino(tcp=[{"port": 443, "state": "aberta", "error": ""}])],
        "allowlist": {"available": True, "count": 1},
        "rejected_targets": [],
    }

    resultados = _por_id(network_connectivity.NetworkConnectivityProcedure().run(_ctx()))
    assert all(r.status is CheckStatus.PASS for r in resultados.values())


def test_falha_de_dns_e_falha_confirmada() -> None:
    _FakeRunner.payload = {"targets": [_destino(resolvido=False)]}

    resultados = _por_id(network_connectivity.NetworkConnectivityProcedure().run(_ctx()))
    assert resultados["network.dns"].status is CheckStatus.FAIL
    assert "intranet.corp.local" in resultados["network.dns"].message


def test_icmp_sem_resposta_gera_apenas_aviso() -> None:
    _FakeRunner.payload = {"targets": [_destino(icmp=False)]}

    resultados = _por_id(network_connectivity.NetworkConnectivityProcedure().run(_ctx()))
    assert resultados["network.icmp"].status is CheckStatus.WARN
    assert resultados["network.icmp"].severity.value == "low"


def test_porta_recusada_e_falha_confirmada() -> None:
    _FakeRunner.payload = {
        "targets": [
            _destino(tcp=[{"port": 443, "state": "recusada", "error": "recusada"}])
        ]
    }

    resultados = _por_id(network_connectivity.NetworkConnectivityProcedure().run(_ctx()))
    assert resultados["network.tcp"].status is CheckStatus.FAIL
    assert "recusada" in resultados["network.tcp"].message


def test_sem_destinos_as_etapas_sao_nao_aplicaveis() -> None:
    _FakeRunner.payload = {"targets": []}

    resultados = _por_id(network_connectivity.NetworkConnectivityProcedure().run(_ctx()))
    assert all(
        r.status is CheckStatus.NOT_APPLICABLE for r in resultados.values()
    )


def test_payload_de_sondagem_usa_as_portas_da_lista(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deskguard.security.allowlist import AllowedTarget, TargetAllowlist

    capturado: dict[str, Any] = {}

    class _Capturador:
        def run_script(self, script, payload=None, *, timeout_s=20.0):  # noqa: ANN001
            capturado.update(payload or {})
            return PowerShellOutcome(
                ok=True, payload={"targets": []}, stdout="", stderr="", duration_ms=1,
                returncode=0,
            )

    monkeypatch.setattr(network_connectivity, "PowerShellRunner", _Capturador)

    allowlist = TargetAllowlist(
        targets=(AllowedTarget(host="intranet.corp.local", ports=(443,)),)
    )
    procedimento = network_connectivity.NetworkConnectivityProcedure()
    procedimento._collect_connectivity(
        _ctx(params={"targets": ["intranet.corp.local"]}, shared={"allowlist": allowlist})
    )

    assert capturado["targets"][0]["host"] == "intranet.corp.local"
    assert capturado["targets"][0]["ports"] == [443]
    assert capturado["timeout_ms"] == 3000


# --------------------------------------------------------------------------
# printers.status
# --------------------------------------------------------------------------


def _impressora(nome="Impressora", status=1, erro=0, extendido=2, offline=False, port="10.0.0.30", driver="Kyocera"):
    return {
        "name": nome,
        "port": port,
        "driver": driver,
        "printer_status": status,
        "detected_error_state": erro,
        "extended_status": extendido,
        "work_offline": offline,
        "is_network": True,
        "is_local": False,
    }


def _payload_impressoras(*, impressoras=None, filas=None, spooler="Running", disponivel=True):
    return {
        "printers.inventory": {
            "available": disponivel,
            "count": len(impressoras or []),
            "printers": impressoras or [],
            "error": "",
        },
        "printers.queue": {
            "included": True,
            "count": len(filas or []),
            "queues": filas or [],
            "error": "",
        },
        "printers.spooler": {
            "name": "Spooler",
            "status": spooler,
            "start_type": "Automatic",
            "available": disponivel,
        },
    }


def test_impressoras_sem_erro_sao_aprovadas() -> None:
    _FakeRunner.payload = _payload_impressoras(impressoras=[_impressora()])

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.inventory"].status is CheckStatus.PASS


def test_erro_reportado_pela_impressora_e_falha_confirmada() -> None:
    _FakeRunner.payload = _payload_impressoras(
        impressoras=[_impressora(status=1, erro=9, extendido=7)]
    )

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.inventory"].status is CheckStatus.FAIL
    assert "9" in resultados["printers.inventory"].message


def test_impressora_offline_marcada_pelo_windows_e_falha() -> None:
    _FakeRunner.payload = _payload_impressoras(
        impressoras=[_impressora(offline=True, status=3)]
    )

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.inventory"].status is CheckStatus.FAIL
    assert resultados["printers.inventory"].severity.value == "high"


def test_impressora_virtual_offline_nao_e_desvio() -> None:
    _FakeRunner.payload = _payload_impressoras(
        impressoras=[
            _impressora(
                nome="Microsoft Print to PDF",
                status=3,
                port="PORTPROMPT:",
                driver="Microsoft Print To PDF",
            )
        ]
    )

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.inventory"].status is CheckStatus.PASS


def test_impressora_fisica_offline_gera_apenas_aviso() -> None:
    _FakeRunner.payload = _payload_impressoras(impressoras=[_impressora(status=3)])

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.inventory"].status is CheckStatus.WARN


def test_sem_impressoras_o_resultado_e_nao_aplicavel() -> None:
    _FakeRunner.payload = _payload_impressoras(impressoras=[])

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.inventory"].status is CheckStatus.NOT_APPLICABLE


def test_trabalho_com_erro_na_fila_e_falha_confirmada() -> None:
    _FakeRunner.payload = _payload_impressoras(
        impressoras=[_impressora()],
        filas=[
            {
                "printer": "Impressora",
                "count": 1,
                "jobs": [
                    {
                        "id": 42,
                        "document": "Contrato.pdf",
                        "user": "usuario",
                        "job_status": 2,
                    }
                ],
            }
        ],
    )

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.queue"].status is CheckStatus.FAIL


def test_fila_vazia_e_aprovada() -> None:
    _FakeRunner.payload = _payload_impressoras(
        impressoras=[_impressora()],
        filas=[{"printer": "Impressora", "count": 0, "jobs": []}],
    )

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.queue"].status is CheckStatus.PASS


def test_spooler_parado_e_falha_confirmada() -> None:
    _FakeRunner.payload = _payload_impressoras(
        impressoras=[_impressora()], spooler="Stopped"
    )

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.spooler"].status is CheckStatus.FAIL
    assert resultados["printers.spooler"].severity.value == "high"


def test_spooler_indisponivel_e_inconclusivo() -> None:
    _FakeRunner.payload = _payload_impressoras(
        impressoras=[_impressora()], spooler="", disponivel=False
    )

    resultados = _por_id(printers_status.PrintersStatusProcedure().run(_ctx()))
    assert resultados["printers.spooler"].status is CheckStatus.INCONCLUSIVE


# --------------------------------------------------------------------------
# Modo demonstração
# --------------------------------------------------------------------------


def test_modo_demonstracao_marca_os_resultados_como_simulados() -> None:
    from deskguard.domain.enums import ExecutionMode as Modo

    for classe in (
        network_configuration.NetworkConfigurationProcedure,
        network_connectivity.NetworkConnectivityProcedure,
        printers_status.PrintersStatusProcedure,
    ):
        procedimento = classe().for_mode(Modo.DEMO)
        resultados = procedimento.run(_ctx())
        assert resultados
        assert all(r.simulated is True for r in resultados)
        assert all(r.evidence.get("simulated") is True for r in resultados)


def test_scripts_novos_existem_no_pacote() -> None:
    from deskguard.collectors.powershell import script_path

    for nome in (
        "network_configuration.ps1",
        "network_connectivity.ps1",
        "printers_status.ps1",
    ):
        assert script_path(nome).exists()


def test_scripts_novos_sao_ascii_puro() -> None:
    from deskguard.collectors.powershell import script_path

    for nome in (
        "network_configuration.ps1",
        "network_connectivity.ps1",
        "printers_status.ps1",
    ):
        conteudo = script_path(nome).read_bytes()
        assert all(byte < 128 for byte in conteudo), f"{nome} contem bytes nao-ASCII"


def test_scripts_nao_executam_comandos_que_alteram_o_sistema() -> None:
    from deskguard.collectors.powershell import script_path

    proibidos = (
        "Test-Printer",
        "Remove-PrintJob",
        "Restart-Service",
        "Suspend-PrintJob",
        "Resume-PrintJob",
        "Set-Printer",
        "Remove-Printer",
        "Add-Printer",
        "Stop-Service",
        "Start-Service",
        "Set-NetIPAddress",
        "New-NetFirewallRule",
    )
    for nome in (
        "network_configuration.ps1",
        "network_connectivity.ps1",
        "printers_status.ps1",
    ):
        texto = _codigo_execucao(script_path(nome).read_text(encoding="utf-8"))
        for comando in proibidos:
            assert comando not in texto, f"{nome} contem o comando proibido {comando}"


def _codigo_execucao(texto: str) -> str:
    """Remove os comentários do script, deixando apenas o código executado.

    A documentação dos scripts cita justamente os comandos proibidos, para
    registrar o que **não** é feito; a verificação de segurança precisa olhar
    apenas as linhas efetivamente executadas.
    """
    sem_bloco = re.sub(r"<#.*?#>", "", texto, flags=re.DOTALL)
    linhas = [
        linha
        for linha in sem_bloco.splitlines()
        if not linha.strip().startswith("#")
    ]
    return "\n".join(linhas)
