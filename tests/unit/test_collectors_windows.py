"""Testes do executor PowerShell e dos coletores da biblioteca padrão."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from deskguard.collectors import powershell as ps
from deskguard.collectors.python_stdlib import (
    collect_storage,
    dns_lookup,
    is_admin,
    logical_drives,
    tcp_probe,
)
from deskguard.domain.enums import CheckStatus, ExecutionMode
from deskguard.domain.results import CheckResult
from deskguard.errors import CollectorError


def _ctx():
    from deskguard.collectors.base import ProbeContext

    return ProbeContext(
        execution_id="exec-teste",
        mode=ExecutionMode.LIVE,
        timeout_s=5.0,
        params={},
    )


def test_script_do_pacote_e_encontrado() -> None:
    caminho = ps.script_path("system_overview.ps1")
    assert caminho.exists()
    assert caminho.name == "system_overview.ps1"


def test_encode_command_preserva_o_conteudo_do_script() -> None:
    caminho = ps.script_path("system_overview.ps1")
    encoded = ps._encode_command(caminho)
    decoded = base64.b64decode(encoded).decode("utf-16-le")
    original = caminho.read_text(encoding="utf-8")
    assert decoded == original


def test_parse_output_extrai_o_json_final() -> None:
    payload = ps._parse_output('ruído antes\n{"ok": true, "data": {"a": 1}}')
    assert payload["ok"] is True
    assert payload["data"] == {"a": 1}


def test_parse_output_aceita_saida_vazia() -> None:
    assert ps._parse_output("") == {}
    assert ps._parse_output("sem json") == {}


def test_script_inexistente_gera_erro_de_coleta(tmp_path: Path) -> None:
    runner = ps.PowerShellRunner()
    with pytest.raises(CollectorError):
        runner.run_script(tmp_path / "nao_existe.ps1", {}, timeout_s=5.0)


def test_run_collector_converte_falha_em_inconclusiva(tmp_path: Path) -> None:
    runner = ps.PowerShellRunner()
    resultado = runner.run_collector(
        "nao_existe.ps1", {}, _ctx(), check_id="c1", title="Coleta"
    )
    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.error_code == "POWERSHELL_ERROR"


def test_script_grande_falha_com_erro_legivel(tmp_path: Path) -> None:
    """Script acima do limite da linha de comando vira erro compreensível.

    Sem essa proteção, o Windows devolve WinError 206 ("nome do arquivo ou a
    extensão é muito grande"), que não diz nada sobre a causa real.
    """
    caminho = tmp_path / "grande.ps1"
    caminho.write_text("x" * 40_000, encoding="utf-8")

    runner = ps.PowerShellRunner()
    with pytest.raises(CollectorError) as erro:
        runner.run_script(caminho, {}, timeout_s=5.0)

    assert "limite" in str(erro.value)
    assert "grande.ps1" in str(erro.value)


def test_scripts_do_pacote_cabem_no_limite_da_linha_de_comando() -> None:
    """Nenhum script versionado pode estourar o limite do Windows."""
    from deskguard.collectors.powershell import script_path

    for nome in (
        "network_configuration.ps1",
        "network_connectivity.ps1",
        "printers_status.ps1",
        "security_audit.ps1",
        "services_status.ps1",
        "system_overview.ps1",
    ):
        encoded = ps._encode_command(script_path(nome))
        assert len(encoded) <= ps._MAX_ENCODED_COMMAND_CHARS, nome


def test_dns_resolve_nome_local() -> None:
    ok, enderecos, erro = dns_lookup("localhost", timeout_s=5.0)
    assert ok is True
    assert enderecos
    assert erro is None


def test_dns_de_nome_inexistente_nao_confirma_falha_de_rede() -> None:
    ok, enderecos, erro = dns_lookup("host-inexistente-deskguard.invalid", timeout_s=3.0)
    assert ok is False
    assert enderecos == []
    assert erro and "DNS" in erro


def test_tcp_probe_em_porta_fechada() -> None:
    ok, erro = tcp_probe("127.0.0.1", 9, timeout_s=2.0)
    assert ok is False
    assert erro is not None


def test_collect_storage_devolve_unidades() -> None:
    resultado = collect_storage(_ctx())
    assert resultado.check_id == "system.storage"
    assert resultado.status in (
        CheckStatus.PASS,
        CheckStatus.WARN,
        CheckStatus.FAIL,
        CheckStatus.INCONCLUSIVE,
    )
    if resultado.status is not CheckStatus.INCONCLUSIVE:
        assert resultado.evidence["volumes"]


def test_is_admin_retorna_booleano_ou_none() -> None:
    assert is_admin() in (True, False, None)


def test_logical_drives_devolve_lista() -> None:
    unidades = logical_drives()
    assert isinstance(unidades, list)
    assert all(unidade.endswith("\\") for unidade in unidades)
