"""Testes do procedimento ``security.audit`` e da interpretação de segurança.

O objetivo é validar a *interpretação* das evidências de segurança — a parte
que decide se algo é falha confirmada, aviso, inconclusividade ou ausência de
desvio — sem depender do estado real do computador do operador.

Duas garantias são verificadas aqui:

* o script de coleta é somente leitura e não executa comando que altere o
  sistema;
* uma verificação que não pôde ser feita **nunca** vira falha confirmada.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from deskguard.collectors.base import ProbeContext
from deskguard.collectors.powershell import PowerShellOutcome
from deskguard.collectors.security_audit import (
    classify_antivirus,
    classify_firewall,
    classify_settings,
    decode_product_state,
)
from deskguard.domain.enums import Capability, CheckStatus, ExecutionMode, Severity
from deskguard.procedures import security_audit

# --------------------------------------------------------------------------
# Infraestrutura de teste
# --------------------------------------------------------------------------


class _FakeRunner:
    """Substitui o executor PowerShell por um resultado pré-definido."""

    payload: dict[str, Any] = {}
    ok = True
    stderr = ""
    returncode = 0
    duracao_ms = 42
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
    monkeypatch.setattr(security_audit, "PowerShellRunner", _FakeRunner)
    return _FakeRunner


def _payload_saudavel() -> dict[str, Any]:
    """Cenário sem desvios: firewall ativo, antivírus atualizado e UAC ativo."""
    return {
        "security.firewall": {
            "available": True,
            "count": 3,
            "profiles": [
                {"name": "Domain", "enabled": "True"},
                {"name": "Private", "enabled": "True"},
                {"name": "Public", "enabled": "True"},
            ],
            "error": "",
            "module_error": "",
        },
        "security.antivirus": {
            "available": True,
            "defender": {
                "available": True,
                "antivirus_enabled": True,
                "realtime_protection": True,
                "signature_age_days": 1,
                "quick_scan_age_days": 1,
                "full_scan_age_days": 2,
                "error": "",
            },
            "products": [{"name": "Windows Defender", "product_state": "397568"}],
            "product_count": 1,
            "error": "",
            "products_error": "",
        },
        "security.settings": {
            "available": True,
            "uac": {
                "available": True,
                "enabled": True,
                "consent_prompt_behavior": 5,
                "prompt_on_secure_desktop": True,
                "error": "",
            },
            "screen_lock": {
                "available": True,
                "screensaver_active": True,
                "timeout_seconds": 600,
                "password_protected": True,
                "error": "",
            },
            "remote_desktop": {"available": True, "enabled": False, "error": ""},
            "encryption": {
                "available": True,
                "protection_status": "On",
                "volume_status": "FullyEncrypted",
                "error": "",
            },
            "guest_account": {
                "available": True,
                "present": False,
                "disabled": None,
                "error": "",
            },
            "error": "",
        },
    }


def _por_id(resultados) -> dict[str, Any]:
    return {resultado.check_id: resultado for resultado in resultados}


def _executar(params: dict[str, Any] | None = None) -> dict[str, Any]:
    return _por_id(security_audit.SecurityAuditProcedure().run(_ctx(params)))


def _status(achados, chave: str) -> CheckStatus | None:
    for achado in achados:
        if achado.key == chave:
            return achado.status
    return None


# --------------------------------------------------------------------------
# Especificação do procedimento
# --------------------------------------------------------------------------


def test_spec_declara_procedimento_de_auditoria() -> None:
    spec = security_audit.SecurityAuditProcedure.spec
    assert spec.id == "security.audit"
    assert spec.category == "Segurança"
    assert spec.capability is Capability.READ_ONLY
    assert spec.privilege.value == "user"
    assert [step.id for step in spec.steps] == [
        "security.firewall",
        "security.antivirus",
        "security.settings",
    ]
    assert spec.risk_notes


def test_parametro_de_prazo_e_limitado() -> None:
    spec = security_audit.SecurityAuditProcedure.spec
    parametro = next(item for item in spec.params if item.name == "stale_threshold_days")
    assert parametro.type == "integer"
    assert parametro.default == 7
    assert parametro.min_value == 1
    assert parametro.max_value == 90


# --------------------------------------------------------------------------
# Firewall
# --------------------------------------------------------------------------


def test_firewall_ativo_em_todos_os_perfis_aprovam() -> None:
    _FakeRunner.payload = _payload_saudavel()
    resultado = _executar()["security.firewall"]
    assert resultado.status is CheckStatus.PASS
    assert resultado.severity is Severity.INFO


def test_firewall_desativado_e_falha_critica() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.firewall"]["profiles"][2]["enabled"] = "False"

    resultado = _executar()["security.firewall"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.CRITICAL
    assert "Público" in resultado.message
    assert resultado.remediation


def test_firewall_com_estado_desconhecido_fica_inconclusivo() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.firewall"]["profiles"][0]["enabled"] = "Unknown"

    resultado = _executar()["security.firewall"]

    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.severity is Severity.INFO


def test_firewall_indisponivel_fica_inconclusivo() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.firewall"]["available"] = False
    _FakeRunner.payload["security.firewall"]["error"] = "modulo indisponivel"

    resultado = _executar()["security.firewall"]

    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.error_code == "FIREWALL_UNAVAILABLE"


def test_classify_firewall_sem_secao_fica_inconclusivo() -> None:
    achados = classify_firewall(None)
    assert len(achados) == 1
    assert achados[0].status is CheckStatus.INCONCLUSIVE


# --------------------------------------------------------------------------
# Antivírus
# --------------------------------------------------------------------------


def test_antivirus_sem_nenhum_produto_e_falha_de_severidade_alta() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.antivirus"]["defender"]["available"] = False
    _FakeRunner.payload["security.antivirus"]["products"] = []
    _FakeRunner.payload["security.antivirus"]["product_count"] = 0

    resultado = _executar()["security.antivirus"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.HIGH


def test_antivirus_com_assinaturas_desatualizadas_e_aviso() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.antivirus"]["defender"]["signature_age_days"] = 30

    resultado = _executar()["security.antivirus"]

    assert resultado.status is CheckStatus.WARN
    assert resultado.severity is Severity.MEDIUM
    assert "30" in resultado.message


def test_prazo_de_desatualizacao_e_configuravel() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.antivirus"]["defender"]["signature_age_days"] = 10

    estrito = _executar({"stale_threshold_days": 7})["security.antivirus"]
    tolerante = _executar({"stale_threshold_days": 30})["security.antivirus"]

    assert estrito.status is CheckStatus.WARN
    assert tolerante.status is CheckStatus.PASS


def test_prazo_de_desatualizacao_fora_do_intervalo_e_limitado() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.antivirus"]["defender"]["signature_age_days"] = 100

    resultado = _executar({"stale_threshold_days": 9000})["security.antivirus"]

    assert resultado.status is CheckStatus.WARN


def test_prazo_de_desatualizacao_invalido_usa_o_padrao() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.antivirus"]["defender"]["signature_age_days"] = 10

    resultado = _executar({"stale_threshold_days": "abc"})["security.antivirus"]

    assert resultado.status is CheckStatus.WARN


def test_protecao_em_tempo_real_desligada_e_falha_alta() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.antivirus"]["defender"]["realtime_protection"] = False

    resultado = _executar()["security.antivirus"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.HIGH


def test_produtos_registrados_sem_estado_conhecido_fica_inconclusivo() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.antivirus"]["defender"]["available"] = False
    _FakeRunner.payload["security.antivirus"]["products"] = [
        {"name": "FortiClient", "product_state": "270352"}
    ]

    resultado = _executar()["security.antivirus"]

    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.severity is Severity.INFO


def test_produtos_registrados_sao_preservados_na_evidencia() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.antivirus"]["defender"]["available"] = False
    _FakeRunner.payload["security.antivirus"]["products"] = [
        {"name": "FortiClient", "product_state": "270352"}
    ]

    resultado = _executar()["security.antivirus"]

    produtos = resultado.evidence["findings"][0]["details"]["products"]
    assert produtos[0]["product_state"] == "270352"
    assert produtos[0]["name"] == "FortiClient"


def test_decode_product_state_reconhece_desativado_e_desatualizado() -> None:
    desativado = decode_product_state("266240")  # 0x041000: protecao desativada
    desatualizado = decode_product_state("0x100000", hexadecimal=True)  # assinaturas antigas

    assert desativado["enabled"] is False
    assert desativado["out_of_date"] is None
    assert desativado["raw"] == "266240"
    assert desativado["decoded_hex"] == "0x041000"
    assert desatualizado["out_of_date"] is True
    assert desatualizado["enabled"] is None


def test_decode_product_state_trata_valor_invalido() -> None:
    resultado = decode_product_state("nao-hex")
    assert resultado["enabled"] is None
    assert resultado["raw"] == "nao-hex"


# --------------------------------------------------------------------------
# Configurações de segurança
# --------------------------------------------------------------------------


def test_uac_desativado_e_falha_alta() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["uac"]["enabled"] = False

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.HIGH


def test_uac_sem_prompt_de_consentimento_e_aviso() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["uac"]["consent_prompt_behavior"] = 0

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.WARN
    assert resultado.severity is Severity.MEDIUM


def test_tela_sem_bloqueio_e_falha() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["screen_lock"]["screensaver_active"] = False

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.MEDIUM


def test_tela_sem_senha_e_falha() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["screen_lock"]["password_protected"] = False

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.MEDIUM


def test_tempo_de_bloqueio_longo_e_aviso_de_baixa_severidade() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["screen_lock"]["timeout_seconds"] = 3600

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.WARN
    assert resultado.severity is Severity.LOW


def test_acesso_remoto_habilitado_e_aviso_de_baixa_severidade() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["remote_desktop"]["enabled"] = True

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.WARN
    assert resultado.severity is Severity.LOW


def test_bitlocker_indisponivel_fica_inconclusivo() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["encryption"]["available"] = False
    _FakeRunner.payload["security.settings"]["encryption"]["error"] = (
        "exige privilegio elevado"
    )

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.error_code == "BITLOCKER_UNAVAILABLE"


def test_bitlocker_desligado_e_falha() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["encryption"]["protection_status"] = "Off"

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.MEDIUM


def test_conta_guest_habilitada_e_falha() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["guest_account"]["present"] = True
    _FakeRunner.payload["security.settings"]["guest_account"]["disabled"] = False

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.MEDIUM


def test_conta_guest_ausente_aprovam() -> None:
    _FakeRunner.payload = _payload_saudavel()
    resultado = _executar()["security.settings"]
    assert resultado.status is CheckStatus.PASS


def test_configuracoes_indisponiveis_ficam_inconclusivas() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.settings"]["uac"]["available"] = False
    _FakeRunner.payload["security.settings"]["screen_lock"]["available"] = False
    _FakeRunner.payload["security.settings"]["remote_desktop"]["available"] = False
    _FakeRunner.payload["security.settings"]["encryption"]["available"] = False
    _FakeRunner.payload["security.settings"]["guest_account"]["available"] = False

    resultado = _executar()["security.settings"]

    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.severity is Severity.INFO


def test_classify_settings_sem_secao_fica_inconclusivo() -> None:
    achados = classify_settings(None)
    assert len(achados) == 1
    assert achados[0].status is CheckStatus.INCONCLUSIVE


# --------------------------------------------------------------------------
# Comportamento do procedimento
# --------------------------------------------------------------------------


def test_execucao_saudavel_aprovam_todas_as_etapas() -> None:
    _FakeRunner.payload = _payload_saudavel()
    resultados = _executar()

    assert set(resultados) == {
        "security.firewall",
        "security.antivirus",
        "security.settings",
    }
    assert all(item.status is CheckStatus.PASS for item in resultados.values())


def test_falha_do_powershell_torna_todas_as_etapas_inconclusivas() -> None:
    _FakeRunner.payload = {}
    _FakeRunner.ok = False
    _FakeRunner.stderr = "erro interno"
    _FakeRunner.returncode = 1

    resultados = _executar()

    assert all(item.status is CheckStatus.INCONCLUSIVE for item in resultados.values())
    assert all(item.error_code == "POWERSHELL_FAILED" for item in resultados.values())


def test_secao_ausente_nao_vira_falha() -> None:
    _FakeRunner.payload = {"security.firewall": {}}

    resultados = _executar()

    assert resultados["security.firewall"].status is CheckStatus.INCONCLUSIVE
    assert resultados["security.antivirus"].status is CheckStatus.INCONCLUSIVE
    assert resultados["security.settings"].status is CheckStatus.INCONCLUSIVE


def test_achados_trazem_impacto_recomendacao_e_referencia() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["security.firewall"]["profiles"][1]["enabled"] = "False"

    resultado = _executar()["security.firewall"]

    achados = resultado.evidence["findings"]
    com_falha = [item for item in achados if item["status"] == "fail"]
    assert com_falha
    assert com_falha[0]["impact"]
    assert com_falha[0]["remediation"]
    assert com_falha[0]["reference"]
    assert com_falha[0]["severity_label"] == "Crítica"


def test_modo_demonstracao_e_simulado() -> None:
    procedure = security_audit.SecurityAuditProcedure()
    demo = procedure.for_mode(ExecutionMode.DEMO)

    resultados = demo.run(_ctx())

    assert resultados
    assert all(item.simulated for item in resultados)
    assert {item.check_id for item in resultados} == {
        "security.firewall",
        "security.antivirus",
        "security.settings",
    }


# --------------------------------------------------------------------------
# Segurança do script de coleta
# --------------------------------------------------------------------------


def _codigo_execucao(texto: str) -> str:
    """Remove os comentários do script, deixando apenas o código executado."""
    sem_bloco = re.sub(r"<#.*?#>", "", texto, flags=re.DOTALL)
    linhas = [
        linha for linha in sem_bloco.splitlines() if not linha.strip().startswith("#")
    ]
    return "\n".join(linhas)


def test_script_e_arquivo_ascii_puro() -> None:
    from deskguard.collectors.powershell import script_path

    conteudo = script_path("security_audit.ps1").read_bytes()
    assert all(byte < 128 for byte in conteudo), "security_audit.ps1 contem bytes nao-ASCII"


def test_script_nao_executa_comandos_que_alteram_o_sistema() -> None:
    from deskguard.collectors.powershell import script_path

    proibidos = (
        "Set-NetFirewallProfile",
        "Set-NetFirewallRule",
        "New-NetFirewallRule",
        "Remove-NetFirewallRule",
        "netsh advfirewall set",
        "Set-MpPreference",
        "Remove-MpPreference",
        "Set-MpComputerStatus",
        "Set-ItemProperty",
        "New-ItemProperty",
        "Remove-ItemProperty",
        "reg add",
        "Enable-WindowsOptionalFeature",
        "Disable-WindowsOptionalFeature",
        "Start-Service",
        "Stop-Service",
        "Restart-Service",
        "Set-Service",
        "sc.exe config",
    )
    texto = _codigo_execucao(script_path("security_audit.ps1").read_text(encoding="utf-8"))
    for comando in proibidos:
        assert comando not in texto, f"security_audit.ps1 contem o comando {comando}"


def test_script_nao_recebe_dados_por_linha_de_comando() -> None:
    from deskguard.collectors.powershell import script_path

    texto = script_path("security_audit.ps1").read_text(encoding="utf-8")
    assert "$args" not in texto
    assert not re.search(r"^param\(", texto, flags=re.MULTILINE)


def test_script_cabe_na_limite_da_linha_de_comando() -> None:
    from deskguard.collectors.powershell import _MAX_ENCODED_COMMAND_CHARS, _encode_command, script_path

    encoded = _encode_command(script_path("security_audit.ps1"))
    assert len(encoded) <= _MAX_ENCODED_COMMAND_CHARS


def test_script_existe_no_pacote() -> None:
    from deskguard.collectors.powershell import script_path

    assert Path("src/deskguard/collectors/scripts/security_audit.ps1").exists()
    assert script_path("security_audit.ps1").exists()
