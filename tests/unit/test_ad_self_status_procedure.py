"""Testes do procedimento ``ad.self_status``.

O procedimento deve usar apenas o contexto de segurança do técnico, sem pedir
credenciais. Os testes validam a interpretação das evidências (conta e
confiança do domínio), o tratamento de indisponibilidade do AD e as garantias
de segurança do script PowerShell.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from deskguard.collectors.ad_status import (
    classify_account,
    classify_domain_trust,
    days_until_expiration,
)
from deskguard.collectors.base import ProbeContext
from deskguard.collectors.powershell import PowerShellOutcome, script_path
from deskguard.domain.enums import Capability, CheckStatus, ExecutionMode, Severity
from deskguard.errors import CollectorError
from deskguard.procedures import ad_self_status

# --------------------------------------------------------------------------
# Infraestrutura de teste
# --------------------------------------------------------------------------


class _FakeRunner:
    """Substitui o executor PowerShell por um resultado pré-definido."""

    payload: dict[str, Any] = {}
    ok = True
    stderr = ""
    returncode = 0
    duracao_ms = 33

    def run_script(self, script, payload=None, *, timeout_s=20.0):  # noqa: ANN001
        return PowerShellOutcome(
            ok=self.ok,
            payload=self.payload,
            stdout="",
            stderr=self.stderr,
            duration_ms=self.duracao_ms,
            returncode=self.returncode,
        )


def _ctx(params: dict[str, Any] | None = None) -> ProbeContext:
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
    monkeypatch.setattr(ad_self_status, "PowerShellRunner", _FakeRunner)
    return _FakeRunner


def _data_futura(dias: int = 90) -> str:
    return (date.today() + timedelta(days=dias)).isoformat() + "T00:00:00"


def _payload_saudavel() -> dict[str, Any]:
    return {
        "ad.account": {
            "username": "tecnico.exemplo",
            "user_domain": "EMPRESA",
            "available": True,
            "enabled": True,
            "locked_out": False,
            "password_expired": False,
            "account_expiration_date": _data_futura(),
            "last_logon_date": "2026-10-23T09:15:00",
            "error": "",
        },
        "ad.domain_trust": {
            "checked": True,
            "trust_ok": True,
            "domain": "empresa.local",
            "error": "",
        },
    }


def _por_id(resultados) -> dict[str, Any]:
    return {resultado.check_id: resultado for resultado in resultados}


def _executar() -> dict[str, Any]:
    return _por_id(ad_self_status.AdSelfStatusProcedure().run(_ctx()))


# --------------------------------------------------------------------------
# Especificação do procedimento
# --------------------------------------------------------------------------


def test_spec_declara_procedimento_somente_leitura_e_sem_admin() -> None:
    spec = ad_self_status.AdSelfStatusProcedure.spec
    assert spec.id == "ad.self_status"
    assert spec.category == "Segurança"
    assert spec.capability is Capability.READ_ONLY
    assert spec.privilege.value == "user"
    assert [step.id for step in spec.steps] == ["ad.account", "ad.domain_trust"]
    assert spec.risk_notes


# --------------------------------------------------------------------------
# Conta do usuário logado
# --------------------------------------------------------------------------


def test_conta_saudavel_aprovam_e_preserva_os_cinco_campos() -> None:
    _FakeRunner.payload = _payload_saudavel()

    resultado = _executar()["ad.account"]

    assert resultado.status is CheckStatus.PASS
    assert resultado.severity is Severity.INFO
    for campo in (
        "enabled",
        "locked_out",
        "password_expired",
        "account_expiration_date",
        "last_logon_date",
    ):
        assert campo in resultado.evidence
    assert resultado.evidence["username"] == "tecnico.exemplo"


def test_conta_bloqueada_e_falha_de_alta_severidade() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["ad.account"]["locked_out"] = True

    resultado = _executar()["ad.account"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.HIGH
    assert "bloqueada" in resultado.message
    assert resultado.remediation


def test_conta_desabilitada_e_falha() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["ad.account"]["enabled"] = False

    resultado = _executar()["ad.account"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.HIGH
    assert "desabilitada" in resultado.message


def test_senha_expirada_e_falha() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["ad.account"]["password_expired"] = True

    resultado = _executar()["ad.account"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.MEDIUM
    assert "senha" in resultado.message.lower()


def test_conta_com_data_de_expiracao_vencida_e_falha() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["ad.account"]["account_expiration_date"] = _data_futura(-2)

    resultado = _executar()["ad.account"]

    assert resultado.status is CheckStatus.FAIL
    assert resultado.severity is Severity.HIGH
    assert resultado.evidence["account_expired"] is True
    assert resultado.evidence["days_until_expiration"] == -2


def test_dias_para_expirar_sao_calculados_a_partir_da_data() -> None:
    referencia = date(2026, 10, 23)
    assert days_until_expiration("2026-11-02T12:00:00", today=referencia) == 10
    assert days_until_expiration("2026-10-20T12:00:00", today=referencia) == -3
    assert days_until_expiration("", today=referencia) is None
    assert days_until_expiration("data-invalida", today=referencia) is None


def test_modulo_ad_indisponivel_fica_inconclusivo() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["ad.account"]["available"] = False
    _FakeRunner.payload["ad.account"]["error"] = "modulo ActiveDirectory ausente"

    resultado = _executar()["ad.account"]

    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.error_code == "AD_ACCOUNT_UNAVAILABLE"
    assert resultado.evidence["error"] == "modulo ActiveDirectory ausente"


def test_campos_incompletos_ficam_inconclusivos() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["ad.account"]["enabled"] = None

    resultado = _executar()["ad.account"]

    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.error_code == "AD_ACCOUNT_INCOMPLETE"


def test_classify_account_sem_secao_fica_inconclusivo() -> None:
    resultado = classify_account(None)
    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.error_code == "MISSING_SECTION"


# --------------------------------------------------------------------------
# Confiança do domínio
# --------------------------------------------------------------------------


def test_confianca_ok_aprovam() -> None:
    _FakeRunner.payload = _payload_saudavel()

    resultado = _executar()["ad.domain_trust"]

    assert resultado.status is CheckStatus.PASS
    assert resultado.evidence["ok"] is True


def test_confianca_quebrada_gera_alerta_com_reparo_administrativo() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["ad.domain_trust"]["trust_ok"] = False

    resultado = _executar()["ad.domain_trust"]

    assert resultado.status is CheckStatus.WARN
    assert resultado.severity is Severity.HIGH
    assert "quebrada" in resultado.message
    assert "administrador" in resultado.message.lower()
    assert "administrador" in (resultado.remediation or "").lower()


def test_confianca_indisponivel_fica_inconclusiva() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["ad.domain_trust"]["checked"] = False
    _FakeRunner.payload["ad.domain_trust"]["error"] = "sem contato com o controlador"

    resultado = _executar()["ad.domain_trust"]

    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.error_code == "TRUST_CHECK_UNAVAILABLE"


def test_classify_domain_trust_sem_secao_fica_inconclusivo() -> None:
    resultado = classify_domain_trust(None)
    assert resultado.status is CheckStatus.INCONCLUSIVE
    assert resultado.error_code == "MISSING_SECTION"


# --------------------------------------------------------------------------
# Comportamento do procedimento
# --------------------------------------------------------------------------


def test_falha_do_powershell_torna_as_duas_etapas_inconclusivas() -> None:
    _FakeRunner.payload = {}
    _FakeRunner.ok = False
    _FakeRunner.stderr = "erro interno"
    _FakeRunner.returncode = 1

    resultados = _executar()

    assert all(item.status is CheckStatus.INCONCLUSIVE for item in resultados.values())
    assert all(item.error_code == "POWERSHELL_FAILED" for item in resultados.values())


def test_powershell_indisponivel_torna_as_duas_etapas_inconclusivas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenRunner:
        def run_script(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise CollectorError("PowerShell não encontrado")

    monkeypatch.setattr(ad_self_status, "PowerShellRunner", _BrokenRunner)

    resultados = _executar()

    assert all(item.status is CheckStatus.INCONCLUSIVE for item in resultados.values())
    assert all(item.error_code == "POWERSHELL_UNAVAILABLE" for item in resultados.values())


def test_resumo_do_dashboard_monta_conta_e_confianca() -> None:
    _FakeRunner.payload = _payload_saudavel()

    resumo = ad_self_status.collect_self_status_summary(timeout_s=5.0)

    assert resumo["username"] == "tecnico.exemplo"
    assert resumo["mode"] == "live"
    assert resumo["account"]["status"] == "pass"
    assert resumo["account"]["enabled"] is True
    assert resumo["domain_trust"]["status"] == "pass"
    assert resumo["domain_trust"]["ok"] is True


def test_resumo_do_dashboard_reflete_confianca_quebrada() -> None:
    _FakeRunner.payload = _payload_saudavel()
    _FakeRunner.payload["ad.domain_trust"]["trust_ok"] = False

    resumo = ad_self_status.collect_self_status_summary(timeout_s=5.0)

    assert resumo["domain_trust"]["status"] == "warn"
    assert resumo["domain_trust"]["ok"] is False
    assert "administrador" in resumo["domain_trust"]["message"].lower()


def test_resumo_do_dashboard_limita_o_tempo_de_coleta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tempos: list[float] = []

    class _ProcedureLenta:
        def run(self, ctx):  # noqa: ANN001
            tempos.append(ctx.timeout_s)
            return []

    monkeypatch.setattr(ad_self_status, "AdSelfStatusProcedure", _ProcedureLenta)

    ad_self_status.collect_self_status_summary(timeout_s=25.0)

    assert tempos == [ad_self_status.DASHBOARD_TIMEOUT_S]


def test_resumo_do_dashboard_captura_falha_inesperada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ProcedureQuebrada:
        def run(self, ctx):  # noqa: ANN001
            raise RuntimeError("falha inesperada")

    monkeypatch.setattr(ad_self_status, "AdSelfStatusProcedure", _ProcedureQuebrada)

    resumo = ad_self_status.collect_self_status_summary(timeout_s=25.0)

    assert resumo["account"]["status"] == "inconclusive"
    assert resumo["domain_trust"]["status"] == "inconclusive"
    assert "RuntimeError" in resumo["account"]["error"]


def test_secoes_ausentes_nao_viram_falha() -> None:
    _FakeRunner.payload = {}

    resultados = _executar()

    assert resultados["ad.account"].status is CheckStatus.INCONCLUSIVE
    assert resultados["ad.domain_trust"].status is CheckStatus.INCONCLUSIVE


def test_modo_demonstracao_e_simulado() -> None:
    demo = ad_self_status.AdSelfStatusProcedure().for_mode(ExecutionMode.DEMO)

    resultados = demo.run(_ctx())

    assert resultados
    assert all(item.simulated for item in resultados)
    assert {item.check_id for item in resultados} == {"ad.account", "ad.domain_trust"}
    assert all(item.evidence.get("simulated") is True for item in resultados)


# --------------------------------------------------------------------------
# Segurança do script de coleta
# --------------------------------------------------------------------------


def _codigo_execucao(texto: str) -> str:
    sem_bloco = re.sub(r"<#.*?#>", "", texto, flags=re.DOTALL)
    linhas = [
        linha for linha in sem_bloco.splitlines() if not linha.strip().startswith("#")
    ]
    return "\n".join(linhas)


def test_script_e_arquivo_ascii_puro() -> None:
    conteudo = script_path("ad_self_status.ps1").read_bytes()
    assert all(byte < 128 for byte in conteudo), "ad_self_status.ps1 contem bytes nao-ASCII"


def test_script_usa_username_e_os_cinco_campos_do_ad() -> None:
    texto = script_path("ad_self_status.ps1").read_text(encoding="utf-8")
    assert "$env:USERNAME" in texto
    assert "Get-ADUser" in texto
    assert "Enabled, LockedOut, PasswordExpired, AccountExpirationDate, LastLogonDate" in texto


def test_script_executa_test_computer_secure_channel_verbose() -> None:
    texto = script_path("ad_self_status.ps1").read_text(encoding="utf-8")
    assert "Test-ComputerSecureChannel -Verbose" in texto


def test_script_nao_pede_credenciais_nem_altera_contas() -> None:
    proibidos = (
        "Get-Credential",
        "ConvertTo-SecureString",
        "PSCredential",
        "-Credential",
        "Set-ADUser",
        "Set-ADAccountPassword",
        "Unlock-ADAccount",
        "Enable-ADAccount",
        "Disable-ADAccount",
        "Reset-ADServiceAccountPassword",
        "Remove-ADUser",
        "New-ADUser",
        "net user",
        "runas",
    )
    texto = _codigo_execucao(script_path("ad_self_status.ps1").read_text(encoding="utf-8"))
    for comando in proibidos:
        assert comando not in texto, f"ad_self_status.ps1 contem o comando {comando}"


def test_script_nao_recebe_dados_por_linha_de_comando() -> None:
    texto = script_path("ad_self_status.ps1").read_text(encoding="utf-8")
    assert "$args" not in texto
    assert not re.search(r"^param\(", texto, flags=re.MULTILINE)


def test_script_cabe_na_limite_da_linha_de_comando() -> None:
    from deskguard.collectors.powershell import _MAX_ENCODED_COMMAND_CHARS, _encode_command

    encoded = _encode_command(script_path("ad_self_status.ps1"))
    assert len(encoded) <= _MAX_ENCODED_COMMAND_CHARS


def test_script_existe_no_pacote() -> None:
    assert Path("src/deskguard/collectors/scripts/ad_self_status.ps1").exists()
    assert script_path("ad_self_status.ps1").exists()
