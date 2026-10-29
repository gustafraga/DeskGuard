"""Procedimento ``ad.self_status`` — diagnóstico de AD do usuário logado.

O procedimento usa exclusivamente o contexto de segurança do técnico que
executa o DeskGuard. Não pede senha, token, credencial de administrador nem
elevação: se o módulo ActiveDirectory não estiver disponível ou o usuário não
tiver leitura sobre a própria conta, o resultado fica inconclusivo.

São duas verificações:

* ``ad.account`` — os cinco campos da conta do usuário atual no AD;
* ``ad.domain_trust`` — o resultado de ``Test-ComputerSecureChannel -Verbose``.
  Quando ``False``, a confiança do computador com o domínio está quebrada e o
  reparo exige privilégio de administrador.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from deskguard.catalog.registry import register
from deskguard.collectors.ad_status import (
    ACCOUNT_CHECK_ID,
    TRUST_CHECK_ID,
    classify_account,
    classify_domain_trust,
)
from deskguard.collectors.base import Collector, ProbeContext
from deskguard.collectors.demo import build_demo_ad_self_status
from deskguard.collectors.powershell import PowerShellRunner, script_path
from deskguard.domain.enums import Capability, ExecutionMode, PrivilegeLevel
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ProcedureSpec, StepSpec
from deskguard.errors import CollectorError
from deskguard.procedures.base import Procedure

_SCRIPT_NAME = "ad_self_status.ps1"

DASHBOARD_TIMEOUT_S = 3.0
_DASHBOARD_ERROR_MESSAGE = (
    "Não foi possível consultar o Active Directory; resultado inconclusivo."
)


@register
class AdSelfStatusProcedure(Procedure):
    """Diagnóstico da conta do usuário logado e da confiança do domínio."""

    spec = ProcedureSpec(
        id="ad.self_status",
        title="Active Directory — conta do usuário logado",
        category="Segurança",
        summary=(
            "Consulta a conta do usuário logado no Active Directory e "
            "verifica a confiança do computador com o domínio, sem pedir "
            "credenciais extras."
        ),
        description=(
            "Usa o contexto de segurança do próprio técnico para consultar o "
            "usuário atual com Get-ADUser e testar o canal seguro com o "
            "controlador de domínio. Não solicita senha, token nem privilégio "
            "de administrador. A conta é avaliada como ativa/desabilitada, "
            "bloqueada, com senha expirada e com a data de expiração; o canal "
            "seguro é apresentado como OK quando Test-ComputerSecureChannel "
            "retorna True. Um retorno False é um alerta de confiança quebrada "
            "e o reparo exige privilégios de administrador."
        ),
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=(
            "Nenhuma configuração, conta ou senha é alterada.",
            "Nenhuma credencial é solicitada: o script usa a identidade Windows do técnico.",
            "São coletados somente os cinco campos da própria conta e o resultado do teste de canal seguro.",
            "Não há desbloqueio, reativação ou redefinição de senha; o reparo é orientado, nunca executado.",
        ),
        prerequisites=(
            "Computador ingressado em domínio Active Directory.",
            "Módulo ActiveDirectory do PowerShell (RSAT) disponível para o usuário.",
            "Permissão de leitura sobre a própria conta no domínio.",
        ),
        expected_outcomes=(
            "Conta ativa e confiança OK: nenhuma inconclusividade esperada.",
            "Conta bloqueada, desabilitada, com senha expirada ou data de expiração vencida: desvio confirmado.",
            "Test-ComputerSecureChannel retornando False: alerta de confiança quebrada, com reparo administrativo indicado.",
            "Módulo AD ausente, consulta sem permissão ou máquina fora do domínio: resultado inconclusivo.",
        ),
        steps=(
            StepSpec(
                id=ACCOUNT_CHECK_ID,
                title="Conta do usuário logado",
                description=(
                    "Enabled, LockedOut, PasswordExpired, AccountExpirationDate "
                    "e LastLogonDate do usuário atual."
                ),
            ),
            StepSpec(
                id=TRUST_CHECK_ID,
                title="Confiança do domínio",
                description=(
                    "Resultado de Test-ComputerSecureChannel para o canal "
                    "seguro entre o computador e o domínio."
                ),
            ),
        ),
        version="1.0.0",
        tags=("active directory", "domínio", "conta", "confiança", "segurança"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="ad.self_status",
                title="Diagnóstico de Active Directory via PowerShell",
                description=(
                    "Consulta a conta do usuário logado e o canal seguro com o "
                    "domínio, usando o contexto do próprio técnico."
                ),
                fn=self._collect,
            )
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return build_demo_ad_self_status()

    def _collect(self, ctx: ProbeContext) -> list[CheckResult]:
        runner = PowerShellRunner()
        try:
            outcome = runner.run_script(
                script_path(_SCRIPT_NAME),
                {},
                timeout_s=ctx.timeout_s,
            )
        except CollectorError as exc:
            return self._all_inconclusive(
                "Não foi possível executar o diagnóstico de Active Directory.",
                error_code="POWERSHELL_UNAVAILABLE",
                evidence={"detail": str(exc)[:400]},
            )

        if not outcome.ok:
            return self._all_inconclusive(
                "A coleta de Active Directory não produziu dados utilizáveis.",
                error_code="POWERSHELL_FAILED",
                evidence={
                    "stderr": outcome.stderr.strip()[:400],
                    "returncode": outcome.returncode,
                },
            )

        data: dict[str, Any] = outcome.payload
        account = classify_account(self._section(data, ACCOUNT_CHECK_ID))
        trust = classify_domain_trust(self._section(data, TRUST_CHECK_ID))
        return [
            self._with_duration(account, outcome.duration_ms),
            self._with_duration(trust, outcome.duration_ms),
        ]

    @staticmethod
    def _section(data: dict[str, Any], key: str) -> dict[str, Any] | None:
        section = data.get(key)
        return section if isinstance(section, dict) else None

    def _all_inconclusive(
        self, message: str, error_code: str, evidence: dict[str, Any]
    ) -> list[CheckResult]:
        return [
            CheckResult.inconclusive(
                step.id,
                step.title,
                message,
                error_code=error_code,
                evidence=evidence,
            )
            for step in self.spec.steps
        ]

    @staticmethod
    def _with_duration(result: CheckResult, duration_ms: int) -> CheckResult:
        if result.duration_ms is not None:
            return result
        return CheckResult(
            check_id=result.check_id,
            title=result.title,
            status=result.status,
            message=result.message,
            severity=result.severity,
            evidence=result.evidence,
            duration_ms=duration_ms,
            error_code=result.error_code,
            remediation=result.remediation,
            simulated=result.simulated,
        )


def inconclusive_self_status_summary(
    message: str = _DASHBOARD_ERROR_MESSAGE, detail: str = ""
) -> dict[str, Any]:
    """Payload de fallback para o Dashboard quando a coleta não é possível."""
    evidence = {"error": detail[:400]} if detail else {}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": str(ExecutionMode.LIVE),
        "username": "",
        "account": {
            "status": "inconclusive",
            "severity": "info",
            "message": message,
            **evidence,
        },
        "domain_trust": {
            "status": "inconclusive",
            "severity": "info",
            "message": message,
            **evidence,
        },
    }


def collect_self_status_summary(timeout_s: float = DASHBOARD_TIMEOUT_S) -> dict[str, Any]:
    """Executa o diagnóstico e devolve um payload pronto para o Dashboard.

    A rota HTTP usa esta função para montar os cards "Minha Conta" e
    "Confiança do Domínio". Ela não registra execução no histórico: é uma
    leitura de contexto para o painel, não uma execução do catálogo.

    O tempo é limitado a :data:`DASHBOARD_TIMEOUT_S` para que uma máquina sem
    RSAT ou sem contato com o controlador de domínio não deixe o painel
    travado. Qualquer falha inesperada vira um payload inconclusivo.
    """
    try:
        effective_timeout = max(0.5, min(float(timeout_s), DASHBOARD_TIMEOUT_S))
        procedure = AdSelfStatusProcedure()
        ctx = ProbeContext(
            execution_id="dashboard-ad-self-status",
            mode=ExecutionMode.LIVE,
            timeout_s=effective_timeout,
        )
        checks = procedure.run(ctx)
    except Exception as exc:  # noqa: BLE001 - o painel nunca deve travar
        return inconclusive_self_status_summary(
            detail=f"{type(exc).__name__}: {exc}"
        )

    by_id = {check.check_id: check for check in checks}
    account = by_id.get(ACCOUNT_CHECK_ID)
    trust = by_id.get(TRUST_CHECK_ID)

    account_payload: dict[str, Any] = {
        "status": str(account.status) if account else "inconclusive",
        "message": account.message if account else "Conta não coletada.",
        "severity": str(account.severity) if account else "info",
    }
    if account:
        account_payload.update(account.evidence)

    trust_payload: dict[str, Any] = {
        "status": str(trust.status) if trust else "inconclusive",
        "message": trust.message if trust else "Confiança não coletada.",
        "severity": str(trust.severity) if trust else "info",
    }
    if trust:
        trust_payload.update(trust.evidence)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": str(ExecutionMode.LIVE),
        "username": account_payload.get("username") or "",
        "account": account_payload,
        "domain_trust": trust_payload,
    }
