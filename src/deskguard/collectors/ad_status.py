"""Interpretação do diagnóstico de Active Directory do usuário logado.

O procedimento ``ad.self_status`` usa apenas o contexto de segurança de quem
executa o DeskGuard: não recebe senha, token nem credencial administrativa.
Este módulo traduz as evidências brutas de ``ad_self_status.ps1`` em resultados
do domínio do DeskGuard.

Princípios:

1. **Nunca inventar falha.** Se o módulo ActiveDirectory não estiver instalado,
   se o usuário não puder ser consultado ou se o canal seguro não puder ser
   testado, o resultado é *inconclusivo*.
2. **Separar conta e confiança.** Os dois checks têm causas e reparos
   diferentes: a conta é resolvida no Active Directory; a confiança do
   computador exige reparo local com privilégio administrativo.
3. **Não coletar segredos.** Apenas os cinco campos solicitados ao AD e o
   resultado do teste de canal seguro são preservados.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from deskguard.domain.enums import CheckStatus, Severity
from deskguard.domain.results import CheckResult

ACCOUNT_CHECK_ID = "ad.account"
TRUST_CHECK_ID = "ad.domain_trust"

ACCOUNT_TITLE = "Conta do usuário logado"
TRUST_TITLE = "Confiança do domínio"

_DISABLED_MESSAGE = "A conta do usuário está desabilitada no Active Directory."
_LOCKED_MESSAGE = "A conta do usuário está bloqueada no Active Directory."
_PASSWORD_EXPIRED_MESSAGE = "A senha da conta está expirada no Active Directory."
_EXPIRED_ACCOUNT_MESSAGE = "A data de expiração da conta já passou."

_DISABLED_REMEDIATION = (
    "Solicitar ao administrador do Active Directory a reativação da conta."
)
_LOCKED_REMEDIATION = (
    "Solicitar o desbloqueio da conta ao administrador do domínio."
)
_PASSWORD_REMEDIATION = (
    "Redefinir a senha no domínio e entrar novamente com a nova credencial."
)
_EXPIRED_ACCOUNT_REMEDIATION = (
    "Solicitar ao administrador do domínio a extensão da data de expiração da conta."
)
_TRUST_REMEDIATION = (
    "O reparo do canal seguro exige privilégio de administrador. "
    "Executar o reparo da confiança do computador com uma conta administrativa "
    "do domínio e reiniciar o equipamento."
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "sim", "yes"):
            return True
        if normalized in ("false", "0", "nao", "não", "no"):
            return False
    return None


def days_until_expiration(
    value: Any, today: date | None = None
) -> int | None:
    """Calcula quantos dias faltam para a data de expiração da conta.

    Aceita ``datetime``/``date`` ou uma string ISO emitida pelo script. Uma
    data já passada devolve um número negativo; ausência de data devolve
    ``None`` (conta sem expiração definida).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        day = value.date()
    elif isinstance(value, date):
        day = value
    else:
        text = _as_text(value)
        if not text:
            return None
        try:
            day = date.fromisoformat(text[:10])
        except ValueError:
            return None
    return (day - (today or date.today())).days


def classify_account(section: dict[str, Any] | None) -> CheckResult:
    """Classifica o estado da conta do usuário logado."""
    if not isinstance(section, dict):
        return CheckResult.inconclusive(
            ACCOUNT_CHECK_ID,
            ACCOUNT_TITLE,
            "A coleta não retornou dados da conta do usuário logado.",
            error_code="MISSING_SECTION",
        )

    username = _as_text(section.get("username"))
    enabled = _as_bool(section.get("enabled"))
    locked_out = _as_bool(section.get("locked_out"))
    password_expired = _as_bool(section.get("password_expired"))
    expiration_raw = _as_text(section.get("account_expiration_date"))
    last_logon_raw = _as_text(section.get("last_logon_date"))
    days_left = days_until_expiration(expiration_raw)
    account_expired = days_left is not None and days_left < 0

    evidence: dict[str, Any] = {
        "username": username,
        "user_domain": _as_text(section.get("user_domain")),
        "available": bool(section.get("available")),
        "enabled": enabled,
        "locked_out": locked_out,
        "password_expired": password_expired,
        "account_expiration_date": expiration_raw or None,
        "last_logon_date": last_logon_raw or None,
        "days_until_expiration": days_left,
        "account_expired": account_expired,
        "error": _as_text(section.get("error")),
    }

    if not section.get("available") or not username:
        return CheckResult.inconclusive(
            ACCOUNT_CHECK_ID,
            ACCOUNT_TITLE,
            "Não foi possível consultar a conta no Active Directory.",
            error_code="AD_ACCOUNT_UNAVAILABLE",
            evidence=evidence,
        )

    if enabled is None or locked_out is None or password_expired is None:
        return CheckResult.inconclusive(
            ACCOUNT_CHECK_ID,
            ACCOUNT_TITLE,
            "O Active Directory respondeu sem todos os campos necessários "
            "para avaliar a conta.",
            error_code="AD_ACCOUNT_INCOMPLETE",
            evidence=evidence,
        )

    problems: list[str] = []
    remediations: list[str] = []
    severities: list[Severity] = []

    if not enabled:
        problems.append(_DISABLED_MESSAGE)
        remediations.append(_DISABLED_REMEDIATION)
        severities.append(Severity.HIGH)

    if locked_out:
        problems.append(_LOCKED_MESSAGE)
        remediations.append(_LOCKED_REMEDIATION)
        severities.append(Severity.HIGH)

    if password_expired:
        problems.append(_PASSWORD_EXPIRED_MESSAGE)
        remediations.append(_PASSWORD_REMEDIATION)
        severities.append(Severity.MEDIUM)

    if account_expired:
        problems.append(_EXPIRED_ACCOUNT_MESSAGE)
        remediations.append(_EXPIRED_ACCOUNT_REMEDIATION)
        severities.append(Severity.HIGH)

    if problems:
        return CheckResult.fail(
            ACCOUNT_CHECK_ID,
            ACCOUNT_TITLE,
            " ".join(problems),
            severity=Severity.max(severities),
            evidence=evidence,
            remediation=" ".join(remediations),
        )

    return CheckResult.ok(
        ACCOUNT_CHECK_ID,
        ACCOUNT_TITLE,
        "Conta ativa, desbloqueada e com senha válida.",
        evidence=evidence,
    )


def classify_domain_trust(section: dict[str, Any] | None) -> CheckResult:
    """Classifica o resultado de ``Test-ComputerSecureChannel``."""
    if not isinstance(section, dict):
        return CheckResult.inconclusive(
            TRUST_CHECK_ID,
            TRUST_TITLE,
            "A coleta não retornou o resultado da confiança do domínio.",
            error_code="MISSING_SECTION",
        )

    checked = bool(section.get("checked"))
    trust_ok = _as_bool(section.get("trust_ok"))
    evidence: dict[str, Any] = {
        "checked": checked,
        "ok": trust_ok,
        "domain": _as_text(section.get("domain")),
        "error": _as_text(section.get("error")),
    }

    if not checked or trust_ok is None:
        return CheckResult.inconclusive(
            TRUST_CHECK_ID,
            TRUST_TITLE,
            "Não foi possível verificar a confiança do computador com o domínio.",
            error_code="TRUST_CHECK_UNAVAILABLE",
            evidence=evidence,
        )

    if trust_ok:
        return CheckResult.ok(
            TRUST_CHECK_ID,
            TRUST_TITLE,
            "A confiança do computador com o domínio está OK.",
            evidence=evidence,
        )

    return CheckResult.warning(
        TRUST_CHECK_ID,
        TRUST_TITLE,
        "A confiança do computador com o domínio está quebrada. "
        "O reparo exige privilégios de administrador.",
        severity=Severity.HIGH,
        evidence=evidence,
        remediation=_TRUST_REMEDIATION,
    )
