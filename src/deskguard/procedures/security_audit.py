"""Procedimento ``security.audit`` — auditoria de segurança do endpoint.

Coleta estritamente somente leitura: consulta o estado do Windows Firewall
por perfil, a proteção antivírus em execução e um conjunto de configurações
básicas de segurança (UAC, bloqueio de tela, acesso remoto, criptografia do
disco e conta de convidado).

Cada achado é classificado por **severidade** e vem acompanhado de impacto,
recomendação e referência documentada. O procedimento nunca afirma que o
equipamento está "totalmente seguro": ele distingue o que foi verificado e
aprovado, o que tem desvio confirmado, o que não pôde ser verificado e o que
não se aplica a este endpoint.
"""

from __future__ import annotations

from typing import Any

from deskguard.catalog.registry import register
from deskguard.collectors.base import Collector, ProbeContext
from deskguard.collectors.demo import build_demo_security_audit
from deskguard.collectors.powershell import PowerShellRunner, script_path
from deskguard.collectors.security_audit import (
    SecurityFinding,
    classify_antivirus,
    classify_firewall,
    classify_settings,
)
from deskguard.domain.enums import Capability, CheckStatus, PrivilegeLevel, Severity
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ParamSpec, ProcedureSpec, StepSpec
from deskguard.errors import CollectorError
from deskguard.procedures.base import Procedure

_SCRIPT_NAME = "security_audit.ps1"

_LIMITE_ITENS_MENSAGEM = 4

_STALE_THRESHOLD_MIN = 1
_STALE_THRESHOLD_MAX = 90
_STALE_THRESHOLD_DEFAULT = 7


def _resumir(itens: list[str], limite: int = _LIMITE_ITENS_MENSAGEM) -> str:
    """Junta os itens em uma mensagem legível, sem esconder a contagem."""
    if not itens:
        return ""
    if len(itens) <= limite:
        return "; ".join(itens)
    restantes = len(itens) - limite
    return "; ".join(itens[:limite]) + f" (e mais {restantes})"


@register
class SecurityAuditProcedure(Procedure):
    """Auditoria de segurança do endpoint: firewall, antivírus e configurações."""

    spec = ProcedureSpec(
        id="security.audit",
        title="Auditoria de segurança do endpoint",
        category="Segurança",
        summary=(
            "Verifica o Windows Firewall em todos os perfis, a proteção "
            "antivírus em execução e as configurações básicas de segurança: "
            "UAC, bloqueio de tela, acesso remoto, criptografia do disco e "
            "conta de convidado."
        ),
        description=(
            "Reúne as evidências de segurança do endpoint e classifica cada "
            "achado por severidade, com impacto, recomendação e referência "
            "documentada. O que não pôde ser verificado — por falta de "
            "privilégio elevado ou de um componente indisponível — é marcado "
            "como inconclusivo, nunca como falha. O resultado descreve a "
            "postura de segurança observada no momento da coleta; não é uma "
            "certificação de que o equipamento esteja seguro."
        ),
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=(
            "Nenhuma configuração é alterada: o procedimento apenas lê o estado do Windows.",
            "Não habilita, desabilita nem reconfigura firewall, antivírus, UAC, BitLocker ou serviços.",
            "Coleta nomes de produtos antivírus registrados, estado dos perfis de firewall e valores de configuração.",
            "A consulta de conta é restrita à conta de convidado (Guest); nenhuma lista de contas de usuário é coletada.",
        ),
        prerequisites=(
            "Windows com o módulo NetSecurity (Windows Defender Firewall) disponível.",
            "Acesso de leitura ao registro do usuário corrente e ao registro do sistema.",
            "A leitura do BitLocker exige privilégio elevado; sem ele, o item fica inconclusivo.",
        ),
        expected_outcomes=(
            "Firewall ativo em todos os perfis e proteção antivírus em execução: nenhuma inconclusividade esperada.",
            "Firewall desativado em um perfil: desvio confirmado de severidade crítica.",
            "Nenhuma proteção antivírus registrada ou desativada: desvio confirmado de severidade alta.",
            "Assinaturas ou varredura desatualizadas: aviso de severidade média.",
            "Configuração ausente, indisponível ou sem permissão: resultado inconclusivo, não falha.",
        ),
        params=(
            ParamSpec(
                name="stale_threshold_days",
                label="Prazo de desatualização (dias)",
                type="integer",
                default=_STALE_THRESHOLD_DEFAULT,
                min_value=_STALE_THRESHOLD_MIN,
                max_value=_STALE_THRESHOLD_MAX,
                help_text=(
                    "Dias sem atualização de assinaturas ou sem varredura rápida "
                    "para que o item seja tratado como desatualizado."
                ),
            ),
        ),
        steps=(
            StepSpec(
                id="security.firewall",
                title="Windows Firewall por perfil",
                description="Estado do firewall nos perfis Domínio, Privado e Público.",
            ),
            StepSpec(
                id="security.antivirus",
                title="Proteção antivírus",
                description=(
                    "Motor de proteção em execução, idade das assinaturas e "
                    "tempo desde a última varredura."
                ),
            ),
            StepSpec(
                id="security.settings",
                title="Configurações de segurança",
                description=(
                    "UAC, bloqueio de tela, acesso remoto, criptografia do "
                    "disco e conta de convidado."
                ),
            ),
        ),
        version="1.0.0",
        tags=("segurança", "firewall", "antivírus", "uac", "bitlocker", "auditoria"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="security.audit",
                title="Auditoria de segurança via PowerShell",
                description=(
                    "Coleta o estado de segurança do Windows (somente leitura)."
                ),
                fn=self._collect_security,
            )
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return build_demo_security_audit()

    # ------------------------------------------------------------------
    # Coleta
    # ------------------------------------------------------------------
    def _collect_security(self, ctx: ProbeContext) -> list[CheckResult]:
        limite = self._stale_threshold(ctx)
        runner = PowerShellRunner()
        try:
            outcome = runner.run_script(
                script_path(_SCRIPT_NAME),
                {},
                timeout_s=ctx.timeout_s,
            )
        except CollectorError as exc:
            return self._all_inconclusive(
                "Não foi possível executar a auditoria de segurança.",
                error_code="POWERSHELL_UNAVAILABLE",
                evidence={"detail": str(exc)[:400]},
            )

        if not outcome.ok:
            return self._all_inconclusive(
                "A coleta de segurança não produziu dados utilizáveis.",
                error_code="POWERSHELL_FAILED",
                evidence={
                    "stderr": outcome.stderr.strip()[:400],
                    "returncode": outcome.returncode,
                },
            )

        data: dict[str, Any] = outcome.payload
        return [
            self._consolidar(
                "security.firewall",
                "Windows Firewall por perfil",
                classify_firewall(self._section(data, "security.firewall")),
                duration_ms=outcome.duration_ms,
                frase_ok="Windows Firewall ativo em todos os perfis consultados.",
            ),
            self._consolidar(
                "security.antivirus",
                "Proteção antivírus",
                classify_antivirus(
                    self._section(data, "security.antivirus"), limite
                ),
                duration_ms=outcome.duration_ms,
                frase_ok="Proteção antivírus em execução.",
            ),
            self._consolidar(
                "security.settings",
                "Configurações de segurança",
                classify_settings(self._section(data, "security.settings")),
                duration_ms=outcome.duration_ms,
                frase_ok="Nenhum desvio confirmado nas configurações de segurança.",
            ),
        ]

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------
    def _stale_threshold(self, ctx: ProbeContext) -> int:
        """Limite de dias usado para considerar assinaturas/varredura antigas."""
        try:
            valor = int(ctx.param("stale_threshold_days", _STALE_THRESHOLD_DEFAULT))
        except (TypeError, ValueError):
            valor = _STALE_THRESHOLD_DEFAULT
        return max(_STALE_THRESHOLD_MIN, min(_STALE_THRESHOLD_MAX, valor))

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

    def _section(self, data: dict[str, Any], key: str) -> dict[str, Any] | None:
        section = data.get(key)
        return section if isinstance(section, dict) else None

    # ------------------------------------------------------------------
    # Consolidação
    # ------------------------------------------------------------------
    def _consolidar(
        self,
        check_id: str,
        title: str,
        achados: list[SecurityFinding],
        duration_ms: int,
        *,
        frase_ok: str,
    ) -> CheckResult:
        """Resume os achados de uma etapa em um único resultado.

        A ordem de decisão é a mesma do restante do DeskGuard: desvio
        confirmado domina, aviso vem em seguida e, sem desvios, a existência
        de itens inconclusivos mantém o resultado honesto — um item que não
        pôde ser verificado não vira "aprovado".
        """
        falhas = [item for item in achados if item.status is CheckStatus.FAIL]
        avisos = [item for item in achados if item.status is CheckStatus.WARN]
        incertos = [item for item in achados if item.status is CheckStatus.INCONCLUSIVE]
        aprovados = [item for item in achados if item.status is CheckStatus.PASS]

        evidencia = {
            "findings": [item.to_dict() for item in achados],
            "count": len(achados),
            "passed": [item.key for item in aprovados],
            "inconclusive": [item.key for item in incertos],
            "confirmed_problems": [item.key for item in falhas + avisos],
        }

        if falhas:
            mensagem = _resumir([f"[{item.severity_label}] {item.label}: {item.message}" for item in falhas])
            if avisos:
                mensagem += " | Também em aviso: " + _resumir(
                    [f"[{item.severity_label}] {item.label}: {item.message}" for item in avisos]
                )
            return CheckResult.fail(
                check_id,
                title,
                mensagem,
                severity=Severity.max([item.severity for item in falhas]),
                evidence=evidencia,
                remediation=falhas[0].remediation or None,
                duration_ms=duration_ms,
            )

        if avisos:
            return CheckResult.warning(
                check_id,
                title,
                _resumir([f"[{item.severity_label}] {item.label}: {item.message}" for item in avisos]),
                severity=Severity.max([item.severity for item in avisos]),
                evidence=evidencia,
                remediation=avisos[0].remediation or None,
                duration_ms=duration_ms,
            )

        if incertos:
            return CheckResult.inconclusive(
                check_id,
                title,
                _resumir(
                    [
                        f"{item.label}: {item.message}"
                        for item in incertos
                    ]
                ),
                error_code=incertos[0].error_code,
                evidence=evidencia,
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            check_id,
            title,
            frase_ok,
            evidence=evidencia,
            duration_ms=duration_ms,
        )
