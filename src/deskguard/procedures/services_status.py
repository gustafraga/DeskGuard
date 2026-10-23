"""Procedimento ``services.status`` — estado dos serviços essenciais do Windows.

Coleta estritamente somente leitura: consulta o estado atual e o tipo de
inicialização dos serviços que sustentam o atendimento (fila de impressão,
cliente DNS, cliente DHCP, rede sem fio e Windows Update) e a cadeia de
dependências entre eles.

Nenhuma ação sobre os serviços é executada: o catálogo não inclui iniciar,
parar, reiniciar ou reconfigurar serviço algum. O serviço Spooler, por
exemplo, é apenas **lido** — reiniciá-lo continua fora do escopo do DeskGuard.
"""

from __future__ import annotations

from typing import Any

from deskguard.catalog.registry import register
from deskguard.collectors.base import Collector, ProbeContext
from deskguard.collectors.demo import build_demo_services_status
from deskguard.collectors.powershell import PowerShellRunner, script_path
from deskguard.collectors.service_status import (
    ServiceProfile,
    ServiceState,
    classify_service,
    classify_startup,
    normalize_service_name,
    profile_for,
)
from deskguard.domain.enums import Capability, CheckStatus, PrivilegeLevel, Severity
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ParamSpec, ProcedureSpec, StepSpec
from deskguard.errors import CollectorError
from deskguard.procedures.base import Procedure

_SCRIPT_NAME = "services_status.ps1"

_LIMITE_ITENS_MENSAGEM = 3


def _resumir(itens: list[str], limite: int = _LIMITE_ITENS_MENSAGEM) -> str:
    """Junta os itens em uma mensagem legível, sem esconder a contagem."""
    if not itens:
        return ""
    if len(itens) <= limite:
        return "; ".join(itens)
    restantes = len(itens) - limite
    return "; ".join(itens[:limite]) + f" (e mais {restantes})"


@register
class ServicesStatusProcedure(Procedure):
    """Estado dos serviços essenciais do Windows e suas dependências."""

    spec = ProcedureSpec(
        id="services.status",
        title="Estado dos serviços do Windows",
        category="Serviços",
        summary=(
            "Verifica o estado e o tipo de inicialização dos serviços que "
            "sustentam o atendimento: fila de impressão, cliente DNS, cliente "
            "DHCP, rede sem fio e Windows Update."
        ),
        description=(
            "Reúne o estado atual dos serviços essenciais do endpoint e "
            "identifica serviços parados que deveriam estar em execução, "
            "serviços desativados e serviços de inicialização manual que "
            "não sobem após um reinício. Acompanha também a cadeia de "
            "dependências, para dizer qual serviço parado derruba os demais. "
            "É o procedimento de partida para reclamações de 'a impressora não "
            "imprime', 'o computador não resolve nomes' e 'o Wi-Fi sumiu'. "
            "Todas as operações são estritamente de leitura."
        ),
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=(
            "Nenhuma ação é executada sobre os serviços.",
            "Não inicia, não para, não reinicia e não reconfigura serviço algum.",
            "Coleta nomes de serviço, estado, tipo de inicialização e caminho do executável.",
        ),
        prerequisites=(
            "Windows com o Gerenciador de Controle de Serviço disponível.",
            "Permissões de leitura sobre o SCM (Service Control Manager).",
        ),
        expected_outcomes=(
            "Serviços essenciais em execução com inicialização automática: nenhuma inconclusividade esperada.",
            "Serviço crítico parado com inicialização automática: desvio confirmado.",
            "Serviço desativado: desvio confirmado em serviços críticos e aviso nos demais.",
            "Serviço de disparo por evento (Windows Update, BITS) parado: estado esperado, não é falha.",
            "Serviço inexistente no endpoint: resultado não aplicável, e não falha.",
        ),
        params=(
            ParamSpec(
                name="include_supporting",
                label="Incluir serviços auxiliares",
                type="boolean",
                default=True,
                help_text=(
                    "Coleta também WMI, RPC, DCOM, BITS e a política de "
                    "diagnóstico. Desativado para um relatório mais enxuto."
                ),
            ),
        ),
        steps=(
            StepSpec(
                id="services.inventory",
                title="Estado dos serviços",
                description="Situação atual dos serviços essenciais monitorados.",
            ),
            StepSpec(
                id="services.startup",
                title="Tipo de inicialização",
                description="Se cada serviço volta a subir após um reinício.",
            ),
            StepSpec(
                id="services.dependencies",
                title="Dependências entre serviços",
                description="Serviços dos quais cada um depende e serviços que dependem dele.",
            ),
        ),
        version="1.0.0",
        tags=("serviço", "serviços", "spooler", "dns", "dhcp", "wlan", "update"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="services.status",
                title="Estado dos serviços via PowerShell",
                description=(
                    "Consulta o Gerenciador de Controle de Serviço (somente leitura)."
                ),
                fn=self._collect_services,
            )
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return build_demo_services_status()

    # ------------------------------------------------------------------
    # Coleta
    # ------------------------------------------------------------------
    def _collect_services(self, ctx: ProbeContext) -> list[CheckResult]:
        include_supporting = bool(ctx.param("include_supporting", True))
        runner = PowerShellRunner()
        try:
            outcome = runner.run_script(
                script_path(_SCRIPT_NAME),
                {"include_supporting": include_supporting},
                timeout_s=ctx.timeout_s,
            )
        except CollectorError as exc:
            return self._all_inconclusive(
                "Não foi possível consultar o estado dos serviços.",
                error_code="POWERSHELL_UNAVAILABLE",
                evidence={"detail": str(exc)[:400]},
            )

        if not outcome.ok:
            return self._all_inconclusive(
                "A coleta do estado dos serviços não produziu dados utilizáveis.",
                error_code="POWERSHELL_FAILED",
                evidence={
                    "stderr": outcome.stderr.strip()[:400],
                    "returncode": outcome.returncode,
                },
            )

        data: dict[str, Any] = outcome.payload
        return [
            self._inventory(data, outcome.duration_ms),
            self._startup(data, outcome.duration_ms),
            self._dependencies(data, outcome.duration_ms),
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

    def _services(self, section: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for item in (section.get("services") or []) if isinstance(item, dict)]

    # ------------------------------------------------------------------
    # Interpretação
    # ------------------------------------------------------------------
    def _inventory(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "services.inventory")
        if section is None:
            return CheckResult.inconclusive(
                "services.inventory",
                "Estado dos serviços",
                "A coleta não retornou o estado dos serviços.",
                error_code="MISSING_SECTION",
            )
        if not section.get("available"):
            return CheckResult.inconclusive(
                "services.inventory",
                "Estado dos serviços",
                "Não foi possível consultar o estado dos serviços neste endpoint.",
                error_code="SERVICES_UNAVAILABLE",
                evidence={"detail": str(section.get("error", ""))[:400]},
            )

        services = self._services(section)
        if not services:
            return CheckResult.inconclusive(
                "services.inventory",
                "Estado dos serviços",
                "A coleta não retornou nenhum serviço monitorado.",
                error_code="NO_SERVICES",
            )

        estados = [self._interpretar_service(servico) for servico in services]
        return self._consolidar(
            "services.inventory",
            "Estado dos serviços",
            estados,
            section,
            duration_ms,
            frase_ok=lambda: (
                f"{len(estados)} serviço(s) monitorado(s) verificado(s), "
                "sem desvio confirmado."
            ),
        )

    def _startup(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "services.inventory")
        if section is None:
            return CheckResult.inconclusive(
                "services.startup",
                "Tipo de inicialização",
                "A coleta não retornou o tipo de inicialização dos serviços.",
                error_code="MISSING_SECTION",
            )
        if not section.get("available"):
            return CheckResult.inconclusive(
                "services.startup",
                "Tipo de inicialização",
                "Não foi possível consultar o tipo de inicialização dos serviços.",
                error_code="SERVICES_UNAVAILABLE",
                evidence={"detail": str(section.get("error", ""))[:400]},
            )

        services = self._services(section)
        if not services:
            return CheckResult.inconclusive(
                "services.startup",
                "Tipo de inicialização",
                "A coleta não retornou nenhum serviço monitorado.",
                error_code="NO_SERVICES",
            )

        estados = [
            self._interpretar_startup(servico) for servico in services
        ]
        return self._consolidar(
            "services.startup",
            "Tipo de inicialização",
            estados,
            section,
            duration_ms,
            frase_ok=lambda: (
                f"Tipo de inicialização conforme o padrão do Windows em "
                f"{len(estados)} serviço(s) monitorado(s)."
            ),
        )

    def _dependencies(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "services.dependencies")
        if section is None:
            return CheckResult.inconclusive(
                "services.dependencies",
                "Dependências entre serviços",
                "A coleta não retornou as dependências entre serviços.",
                error_code="MISSING_SECTION",
            )
        if not section.get("available"):
            return CheckResult.inconclusive(
                "services.dependencies",
                "Dependências entre serviços",
                "Não foi possível consultar as dependências entre serviços.",
                error_code="SERVICES_UNAVAILABLE",
                evidence={"detail": str(section.get("error", ""))[:400]},
            )

        inventory = self._section(data, "services.inventory") or {}
        services = self._services(inventory)
        status_por_nome: dict[str, str] = {}
        rotulos: dict[str, str] = {}
        for servico in services:
            chave = normalize_service_name(str(servico.get("name", "")))
            if not chave:
                continue
            status_por_nome[chave] = str(servico.get("status", "Unknown"))
            perfil = profile_for(str(servico.get("name", "")))
            rotulos[chave] = perfil.label if perfil else str(servico.get("name", ""))

        linhas = [row for row in (section.get("dependencies") or []) if isinstance(row, dict)]

        # Dependencia monitorada que esta parada: derruba quem depende dela.
        quebradas: list[str] = []
        for linha in linhas:
            nome = normalize_service_name(str(linha.get("name", "")))
            if not nome or status_por_nome.get(nome) != "Running":
                continue
            for dependencia in linha.get("depends_on") or []:
                chave = normalize_service_name(str(dependencia))
                if chave in status_por_nome and status_por_nome[chave] != "Running":
                    quebradas.append(
                        f"{rotulos.get(nome, nome)} depende de "
                        f"{rotulos.get(chave, chave)}, que está parado"
                    )

        # Servico parado que derruba outros servicos monitorados.
        com_impacto: list[str] = []
        for linha in linhas:
            nome = normalize_service_name(str(linha.get("name", "")))
            if not nome or status_por_nome.get(nome) == "Running":
                continue
            dependentes = [
                normalize_service_name(str(item))
                for item in (linha.get("dependents") or [])
            ]
            afetados = [
                rotulos.get(chave, chave)
                for chave in dependentes
                if chave in status_por_nome
            ]
            if afetados:
                com_impacto.append(
                    f"{rotulos.get(nome, nome)} está parado e derruba "
                    f"{len(afetados)} serviço(s) monitorado(s)"
                )

        evidencia = {
            "dependencies": linhas,
            "monitored": [
                {
                    "name": servico.get("name"),
                    "status": servico.get("status"),
                    "start_type": servico.get("start_type"),
                }
                for servico in services
            ],
            "broken_dependencies": quebradas,
            "stopped_with_impact": com_impacto,
        }

        if quebradas:
            return CheckResult.fail(
                "services.dependencies",
                "Dependências entre serviços",
                _resumir(quebradas),
                severity=Severity.MEDIUM,
                evidence=evidencia,
                remediation=(
                    "Restabelecer o serviço de que depende o serviço em "
                    "funcionamento antes de reavaliar o endpoint."
                ),
                duration_ms=duration_ms,
            )

        if com_impacto:
            return CheckResult.warning(
                "services.dependencies",
                "Dependências entre serviços",
                _resumir(com_impacto),
                severity=Severity.LOW,
                evidence=evidencia,
                remediation=(
                    "Verificar o serviço parado: os serviços que dependem dele "
                    "não voltam a funcionar enquanto ele estiver fora."
                ),
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "services.dependencies",
            "Dependências entre serviços",
            "Nenhuma dependência monitorada está interrompida.",
            evidence=evidencia,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------
    def _interpretar_service(self, servico: dict[str, Any]) -> ServiceState:
        perfil: ServiceProfile | None = profile_for(str(servico.get("name", "")))
        return classify_service(servico, perfil)

    def _interpretar_startup(self, servico: dict[str, Any]) -> ServiceState:
        perfil: ServiceProfile | None = profile_for(str(servico.get("name", "")))
        return classify_startup(servico, perfil)

    def _consolidar(
        self,
        check_id: str,
        title: str,
        estados: list[ServiceState],
        section: dict[str, Any],
        duration_ms: int,
        *,
        frase_ok: Any,
    ) -> CheckResult:
        """Resume os estados interpretados em um único resultado da etapa.

        A regra de agregação é a mesma do restante do DeskGuard: desvio
        confirmado domina, aviso vem em seguida, e services não aplicáveis ou
        inconclusivos não alteram a leitura de um conjunto saudável.
        """
        falhas = [e for e in estados if e.status is CheckStatus.FAIL]
        avisos = [e for e in estados if e.status is CheckStatus.WARN]
        incertos = [e for e in estados if e.status is CheckStatus.INCONCLUSIVE]
        aplicaveis = [e for e in estados if e.status is CheckStatus.NOT_APPLICABLE]

        evidencia = {
            "services": [estado.to_dict() for estado in estados],
            "count": len(estados),
            "not_applicable": [estado.name for estado in aplicaveis],
            "module_error": section.get("module_error") or "",
        }

        if falhas:
            mensagem = _resumir([f"{e.label}: {e.message}" for e in falhas])
            if avisos:
                mensagem += " | Também em aviso: " + _resumir(
                    [f"{e.label}: {e.message}" for e in avisos]
                )
            return CheckResult.fail(
                check_id,
                title,
                mensagem,
                severity=Severity.max([e.severity for e in falhas]),
                evidence=evidencia,
                remediation=falhas[0].impact or None,
                duration_ms=duration_ms,
            )

        if avisos:
            return CheckResult.warning(
                check_id,
                title,
                _resumir([f"{e.label}: {e.message}" for e in avisos]),
                severity=Severity.max([e.severity for e in avisos]),
                evidence=evidencia,
                remediation=avisos[0].impact or None,
                duration_ms=duration_ms,
            )

        if incertos and len(incertos) == len(estados):
            return CheckResult.inconclusive(
                check_id,
                title,
                "Não foi possível determinar o estado de nenhum serviço monitorado.",
                error_code="SERVICE_STATE_UNKNOWN",
                evidence=evidencia,
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            check_id,
            title,
            frase_ok(),
            evidence=evidencia,
            duration_ms=duration_ms,
        )
