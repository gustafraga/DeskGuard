"""Procedimento ``network.configuration`` — configuração de rede do endpoint.

Coleta somente leitura da configuração de IP, gateway, DNS, rotas e do estado
dos adaptadores. Nenhuma configuração é alterada.
"""

from __future__ import annotations

from typing import Any

from deskguard.catalog.registry import register
from deskguard.collectors.base import Collector, ProbeContext
from deskguard.collectors.demo import build_demo_network_configuration
from deskguard.collectors.powershell import PowerShellRunner, script_path
from deskguard.domain.enums import Capability, PrivilegeLevel, Severity
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ProcedureSpec, StepSpec
from deskguard.errors import CollectorError
from deskguard.procedures.base import Procedure

_SCRIPT_NAME = "network_configuration.ps1"


@register
class NetworkConfigurationProcedure(Procedure):
    """Configuração de rede: adaptadores, IP, gateway, DNS e rotas."""

    spec = ProcedureSpec(
        id="network.configuration",
        title="Configuração de rede",
        category="Rede",
        summary=(
            "Levanta a configuração de rede do endpoint: adaptadores, endereços IP, "
            "gateway padrão, servidores DNS e rotas."
        ),
        description=(
            "Reúne a configuração de rede do computador, que é a base de quase todo "
            "atendimento de conectividade. Responde: qual interface está ativa, qual "
            "IP o endpoint usa, se há gateway e servidores DNS configurados e qual "
            "é a categoria da rede. Todas as operações são estritamente de leitura."
        ),
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=(
            "Nenhuma configuração de rede é alterada.",
            "Coleta o endereço MAC e os endereços IP do endpoint (dados de inventário).",
            "Nenhum dado de tráfego, sessão ou credencial é lido.",
        ),
        prerequisites=(
            "Windows com o módulo NetTCPIP disponível.",
            "Permissões de leitura sobre as classes CIM de rede.",
        ),
        expected_outcomes=(
            "Interface ativa com IP e gateway: nenhuma inconclusividade esperada.",
            "Nenhuma interface ativa: desvio confirmado de severidade alta.",
            "Cmdlets indisponíveis: a etapa correspondente fica inconclusiva.",
        ),
        steps=(
            StepSpec(
                id="network.interfaces",
                title="Estado dos adaptadores",
                description="Interfaces ativas, Speed, tipo de mídia, MAC e estado.",
            ),
            StepSpec(
                id="network.ip_configuration",
                title="Endereçamento IP",
                description="Endereços IPv4/IPv6, gateway padrão e servidores DNS.",
            ),
            StepSpec(
                id="network.routes",
                title="Rotas",
                description="Rota padrão e interface associada.",
            ),
            StepSpec(
                id="network.profile",
                title="Perfil de rede",
                description="Categoria da rede e conectividade IPv4/IPv6 informadas pelo Windows.",
            ),
        ),
        version="1.0.0",
        tags=("rede", "ip", "dns", "gateway", "inventário"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="network.configuration",
                title="Configuração de rede via PowerShell",
                description="Consulta as classes de rede do Windows (somente leitura).",
                fn=self._collect_configuration,
            )
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return build_demo_network_configuration()

    # ------------------------------------------------------------------
    # Coleta
    # ------------------------------------------------------------------
    def _collect_configuration(self, ctx: ProbeContext) -> list[CheckResult]:
        runner = PowerShellRunner()
        try:
            outcome = runner.run_script(
                script_path(_SCRIPT_NAME), {}, timeout_s=ctx.timeout_s
            )
        except CollectorError as exc:
            return self._all_inconclusive(
                "Não foi possível consultar a configuração de rede do Windows.",
                error_code="POWERSHELL_UNAVAILABLE",
                evidence={"detail": str(exc)[:400]},
            )

        if not outcome.ok:
            return self._all_inconclusive(
                "A coleta da configuração de rede não produziu dados utilizáveis.",
                error_code="POWERSHELL_FAILED",
                evidence={
                    "stderr": outcome.stderr.strip()[:400],
                    "returncode": outcome.returncode,
                },
            )

        data: dict[str, Any] = outcome.payload
        return [
            self._adapters(data, outcome.duration_ms),
            self._ip_configuration(data, outcome.duration_ms),
            self._routes(data, outcome.duration_ms),
            self._profile(data, outcome.duration_ms),
        ]

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
    # Interpretação
    # ------------------------------------------------------------------
    def _adapters(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "network.interfaces")
        if section is None:
            return CheckResult.inconclusive(
                "network.interfaces",
                "Estado dos adaptadores",
                "A coleta não retornou dados de adaptadores.",
                error_code="MISSING_SECTION",
            )
        if "error" in section:
            return CheckResult.inconclusive(
                "network.interfaces",
                "Estado dos adaptadores",
                "Não foi possível obter o estado dos adaptadores.",
                error_code="COLLECTION_ERROR",
                evidence={"detail": str(section.get("error"))[:400]},
            )

        adapters = list(section.get("adapters") or [])
        if not adapters:
            return CheckResult.inconclusive(
                "network.interfaces",
                "Estado dos adaptadores",
                "Nenhum adaptador de rede foi encontrado neste endpoint.",
                error_code="NO_ADAPTERS",
                evidence=section,
                duration_ms=duration_ms,
            )

        ativos = [a for a in adapters if str(a.get("status")) == "Up"]
        desabilitados = [a for a in adapters if str(a.get("status")) == "Disabled"]

        if not ativos:
            return CheckResult.fail(
                "network.interfaces",
                "Estado dos adaptadores",
                "Nenhuma interface de rede está ativa. Causa confirmada de perda de conectividade.",
                severity=Severity.HIGH,
                evidence=section,
                remediation="Verificar cabo, Wi-Fi, estado do adaptador e configuração da interface.",
                duration_ms=duration_ms,
            )

        if desabilitados:
            return CheckResult.warning(
                "network.interfaces",
                "Estado dos adaptadores",
                f"{len(ativos)} interface(s) ativa(s) e {len(desabilitados)} desabilitada(s).",
                severity=Severity.LOW,
                evidence=section,
                remediation="Confirmar se as interfaces desabilitadas devem estar ativas.",
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "network.interfaces",
            "Estado dos adaptadores",
            f"{len(ativos)} interface(s) de rede ativa(s).",
            evidence=section,
            duration_ms=duration_ms,
        )

    def _ip_configuration(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "network.ip_configuration")
        if section is None:
            return CheckResult.inconclusive(
                "network.ip_configuration",
                "Endereçamento IP",
                "A coleta não retornou a configuração de endereçamento.",
                error_code="MISSING_SECTION",
            )
        if "error" in section:
            return CheckResult.inconclusive(
                "network.ip_configuration",
                "Endereçamento IP",
                "Não foi possível obter a configuração de endereçamento IP.",
                error_code="COLLECTION_ERROR",
                evidence={"detail": str(section.get("error"))[:400]},
            )

        configs = list(section.get("configs") or [])
        utilizaveis = []
        for config in configs:
            for address in config.get("addresses") or []:
                if str(address.get("family")) != "IPv4":
                    continue
                if str(address.get("state")) != "Preferred":
                    continue
                utilizaveis.append((config, address))
                break

        if not utilizaveis:
            return CheckResult.fail(
                "network.ip_configuration",
                "Endereçamento IP",
                "Nenhuma interface possui um endereço IPv4 válido (estado Preferred).",
                severity=Severity.HIGH,
                evidence=section,
                remediation=(
                    "Verificar se o DHCP está respondendo ou se o endereço estático "
                    "foi configurado corretamente."
                ),
                duration_ms=duration_ms,
            )

        sem_gateway = []
        for config, _ in utilizaveis:
            if not config.get("gateways"):
                sem_gateway.append(str(config.get("interface", "")))

        if len(sem_gateway) == len(utilizaveis):
            return CheckResult.warning(
                "network.ip_configuration",
                "Endereçamento IP",
                "Interface(s) com IP válido, mas sem gateway padrão configurado.",
                severity=Severity.MEDIUM,
                evidence=section,
                remediation="Confirmar a configuração do gateway padrão da interface.",
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "network.ip_configuration",
            "Endereçamento IP",
            f"{len(utilizaveis)} interface(s) com endereçamento IPv4 válido e gateway configurado.",
            evidence=section,
            duration_ms=duration_ms,
        )

    def _routes(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "network.routes")
        if section is None:
            return CheckResult.inconclusive(
                "network.routes",
                "Rotas",
                "A coleta não retornou as rotas do sistema.",
                error_code="MISSING_SECTION",
            )
        if "error" in section:
            return CheckResult.inconclusive(
                "network.routes",
                "Rotas",
                "Não foi possível obter as rotas do sistema.",
                error_code="COLLECTION_ERROR",
                evidence={"detail": str(section.get("error"))[:400]},
            )

        routes = list(section.get("default_routes") or [])
        if not routes:
            return CheckResult.warning(
                "network.routes",
                "Rotas",
                "Nenhuma rota padrão (0.0.0.0/0) está configurada.",
                severity=Severity.MEDIUM,
                evidence=section,
                remediation="Confirmar a rota padrão do endpoint.",
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "network.routes",
            "Rotas",
            f"{len(routes)} rota(s) padrão configurada(s).",
            evidence=section,
            duration_ms=duration_ms,
        )

    def _profile(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "network.profile")
        if section is None:
            return CheckResult.inconclusive(
                "network.profile",
                "Perfil de rede",
                "A coleta não retornou o perfil de rede.",
                error_code="MISSING_SECTION",
            )
        if "error" in section:
            return CheckResult.inconclusive(
                "network.profile",
                "Perfil de rede",
                "Não foi possível obter o perfil de rede.",
                error_code="COLLECTION_ERROR",
                evidence={"detail": str(section.get("error"))[:400]},
            )

        profiles = list(section.get("profiles") or [])
        if not profiles:
            return CheckResult.inconclusive(
                "network.profile",
                "Perfil de rede",
                "Nenhuma interface ativa está associada a um perfil de rede do Windows.",
                error_code="NO_PROFILE",
                evidence=section,
                duration_ms=duration_ms,
            )

        sem_conectividade = [
            profile
            for profile in profiles
            if str(profile.get("ipv4_state")) in ("Disconnected", "Unreachable")
        ]
        if sem_conectividade:
            return CheckResult.fail(
                "network.profile",
                "Perfil de rede",
                "O Windows informa a interface como sem conectividade IPv4.",
                severity=Severity.HIGH,
                evidence=section,
                remediation="Verificar endereço IP, gateway e servidores DNS da interface.",
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "network.profile",
            "Perfil de rede",
            f"{len(profiles)} interface(s) com perfil de rede associado.",
            evidence=section,
            duration_ms=duration_ms,
        )
