"""Procedimento ``system.overview`` — visão geral do endpoint Windows.

Coleta somente leitura de inventário: versão do Windows, identidade do
equipamento, tempo de atividade, hardware resumido, contexto de execução e
espaço em disco. Nenhuma configuração do sistema é alterada.
"""

from __future__ import annotations

from typing import Any

from deskguard.catalog.registry import register
from deskguard.collectors.base import Collector, ProbeContext
from deskguard.collectors.demo import build_demo_system_overview
from deskguard.collectors.powershell import PowerShellRunner, script_path
from deskguard.collectors.python_stdlib import collect_runtime, collect_storage
from deskguard.domain.enums import Capability, PrivilegeLevel
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ParamSpec, ProcedureSpec, StepSpec
from deskguard.errors import CollectorError
from deskguard.procedures.base import Procedure

_SCRIPT_NAME = "system_overview.ps1"

_SECTIONS: tuple[tuple[str, str], ...] = (
    ("os.version", "Versão do Windows"),
    ("system.identity", "Identidade do equipamento"),
    ("system.uptime", "Tempo de atividade"),
    ("system.hardware", "Hardware resumido"),
)


@register
class SystemOverviewProcedure(Procedure):
    """Inventário básico do endpoint, útil como primeira etapa de qualquer chamado."""

    spec = ProcedureSpec(
        id="system.overview",
        title="Visão geral do sistema",
        category="Sistema",
        summary="Coleta o inventário básico do endpoint: Windows, hardware, atividade, disco e contexto de execução.",
        description=(
            "Reúne as informações de identificação do computador e o estado geral do "
            "sistema operacional. É o ponto de partida habitual de um atendimento: "
            "confirma o que o usuário está usando antes de investigar a queixa. "
            "Todas as operações são estritamente de leitura."
        ),
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=(
            "Nenhuma configuração do sistema é alterada.",
            "Coleta metadados de inventário (nome do equipamento, fabricante, série, CPU e memória).",
            "A conta em uso só é incluída quando o operador solicita explicitamente.",
        ),
        prerequisites=(
            "Windows com PowerShell 5.1 ou superior disponível.",
            "Serviço Windows Management Instrumentation em execução.",
            "Permissões de leitura sobre as classes CIM consultadas.",
        ),
        expected_outcomes=(
            "Inventário completo: nenhuma inconclusividade esperada.",
            "Versão ou hardware indisponível: a etapa correspondente fica inconclusiva.",
            "Volume com 90% ou mais de uso: desvio confirmado de severidade alta.",
        ),
        params=(
            ParamSpec(
                name="include_account",
                label="Incluir conta em uso",
                type="boolean",
                default=False,
                help_text=(
                    "Inclui o usuário conectado no inventário. Desativado por padrão "
                    "para minimizar coleta de dados pessoais."
                ),
            ),
        ),
        steps=(
            StepSpec(
                id="os.version",
                title="Versão do Windows",
                description="Edição, build, versão de atualização e data de instalação.",
            ),
            StepSpec(
                id="system.identity",
                title="Identidade do equipamento",
                description="Nome do computador, fabricante, modelo, série e domínio.",
            ),
            StepSpec(
                id="system.uptime",
                title="Tempo de atividade",
                description="Último inicialização, tempo em atividade e fuso horário.",
            ),
            StepSpec(
                id="system.hardware",
                title="Hardware resumido",
                description="Processador, contagem de núcleos e memória física total.",
            ),
            StepSpec(
                id="system.runtime",
                title="Contexto de execução",
                description="Privilégio do processo, memória em uso e ambiente do DeskGuard.",
            ),
            StepSpec(
                id="system.storage",
                title="Armazenamento",
                description="Volumes fixos com espaço total, livre e percentual de uso.",
            ),
        ),
        version="1.0.0",
        tags=("inventário", "windows", "primeiro-contato"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="system.windows",
                title="Inventário via PowerShell",
                description="Consulta as classes CIM do Windows para o inventário do endpoint.",
                fn=self._collect_windows,
            ),
            Collector(
                check_id="system.runtime",
                title="Contexto de execução",
                description="Privilégio do processo e uso de memória obtidos via API local.",
                fn=collect_runtime,
            ),
            Collector(
                check_id="system.storage",
                title="Armazenamento",
                description="Volumes fixos obtidos via API de disco do sistema.",
                fn=collect_storage,
            ),
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return build_demo_system_overview()

    def _collect_windows(self, ctx: ProbeContext) -> list[CheckResult]:
        runner = PowerShellRunner()
        payload = {"include_account": bool(ctx.param("include_account", False))}

        try:
            outcome = runner.run_script(
                script_path(_SCRIPT_NAME), payload, timeout_s=ctx.timeout_s
            )
        except CollectorError as exc:
            return [
                CheckResult.inconclusive(
                    section_id,
                    title,
                    "Não foi possível consultar o Windows Management Instrumentation.",
                    error_code="POWERSHELL_UNAVAILABLE",
                    evidence={"detail": str(exc)[:400]},
                )
                for section_id, title in _SECTIONS
            ]

        if not outcome.ok:
            return [
                CheckResult.inconclusive(
                    section_id,
                    title,
                    "A coleta via PowerShell não produziu dados utilizáveis.",
                    error_code="POWERSHELL_FAILED",
                    evidence={
                        "stderr": outcome.stderr.strip()[:400],
                        "returncode": outcome.returncode,
                    },
                    duration_ms=outcome.duration_ms,
                )
                for section_id, title in _SECTIONS
            ]

        data: dict[str, Any] = outcome.payload
        results: list[CheckResult] = []
        for section_id, title in _SECTIONS:
            section = data.get(section_id)
            if not isinstance(section, dict):
                results.append(
                    CheckResult.inconclusive(
                        section_id,
                        title,
                        "A coleta não retornou dados para esta seção.",
                        error_code="MISSING_SECTION",
                        duration_ms=outcome.duration_ms,
                    )
                )
                continue
            if "error" in section:
                results.append(
                    CheckResult.inconclusive(
                        section_id,
                        title,
                        "Não foi possível obter esta informação no endpoint atual.",
                        error_code="COLLECTION_ERROR",
                        evidence={"detail": str(section.get("error"))[:400]},
                        duration_ms=outcome.duration_ms,
                    )
                )
                continue
            results.append(
                CheckResult.ok(
                    section_id,
                    title,
                    "Informação obtida com sucesso.",
                    evidence=section,
                    duration_ms=outcome.duration_ms,
                )
            )
        return results
