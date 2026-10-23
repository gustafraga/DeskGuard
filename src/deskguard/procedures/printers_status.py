"""Procedimento ``printers.status`` — impressoras instaladas, fila e estado.

Coleta somente leitura. Nenhuma ação sobre a impressora ou sobre a fila é
executada: em particular, ``Test-Printer`` (que imprime uma página de teste),
``Remove-PrintJob`` e o reinício do serviço Spooler estão fora do catálogo.
"""

from __future__ import annotations

from typing import Any

from deskguard.catalog.registry import register
from deskguard.collectors.base import Collector, ProbeContext
from deskguard.collectors.demo import build_demo_printers_status
from deskguard.collectors.powershell import PowerShellRunner, script_path
from deskguard.collectors.printer_status import classify_job, classify_printer
from deskguard.domain.enums import Capability, CheckStatus, PrivilegeLevel, Severity
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ParamSpec, ProcedureSpec, StepSpec
from deskguard.errors import CollectorError
from deskguard.procedures.base import Procedure

_SCRIPT_NAME = "printers_status.ps1"

_LIMITE_ITENS_MENSAGEM = 3


def _resumir(itens: list[str], limite: int = _LIMITE_ITENS_MENSAGEM) -> str:
    """Junta os itens em uma mensagem legível, sem esconder a contagem.

    A lista completa continua disponível nas evidências; a mensagem resume
    apenas o que cabe no relatório.
    """
    if not itens:
        return ""
    if len(itens) <= limite:
        return "; ".join(itens)
    restantes = len(itens) - limite
    return "; ".join(itens[:limite]) + f" (e mais {restantes})"


@register
class PrintersStatusProcedure(Procedure):
    """Inventário de impressoras, fila de trabalhos e estado do spooler."""

    spec = ProcedureSpec(
        id="printers.status",
        title="Estado das impressoras",
        category="Impressoras",
        summary=(
            "Lista as impressoras instaladas, indica se estão online ou offline, "
            "lista a fila de trabalhos pendentes e verifica o serviço de impressão."
        ),
        description=(
            "Reúne o estado do subsistema de impressão do endpoint: quais "
            "impressoras estão instaladas e em que estado, se há trabalhos "
            "parados na fila e se o serviço Print Spooler está em execução. "
            "É o procedimento de partida para reclamações de 'a impressora não "
            "imprime'. Todas as operações são estritamente de leitura."
        ),
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=(
            "Nenhuma ação é executada sobre a impressora ou sobre a fila.",
            "Não imprime página de teste, não remove trabalhos e não reinicia o serviço Spooler.",
            "Coleta nomes de impressoras, portas, drivers e o nome de usuário de trabalhos pendentes.",
        ),
        prerequisites=(
            "Windows com o serviço Print Spooler disponível.",
            "Permissões de leitura sobre as classes de impressão do WMI.",
        ),
        expected_outcomes=(
            "Impressoras instaladas e sem erro: nenhuma inconclusividade esperada.",
            "Impressora offline ou com erro reportado: desvio confirmado.",
            "Nenhuma impressora instalada: resultado não aplicável, e não falha.",
            "Fila de impressão inacessível por permissão: leitura da fila inconclusiva.",
        ),
        params=(
            ParamSpec(
                name="include_jobs",
                label="Incluir fila de trabalhos",
                type="boolean",
                default=True,
                help_text=(
                    "Coleta os trabalhos pendentes de cada impressora. Desativado "
                    "para reduzir a exposição de nomes de documentos e usuários."
                ),
            ),
        ),
        steps=(
            StepSpec(
                id="printers.inventory",
                title="Inventário de impressoras",
                description="Impressoras instaladas, porta, driver e estado online/offline.",
            ),
            StepSpec(
                id="printers.queue",
                title="Fila de impressão",
                description="Trabalhos pendentes em cada impressora e situação de cada um.",
            ),
            StepSpec(
                id="printers.spooler",
                title="Serviço de impressão",
                description="Estado do serviço Print Spooler.",
            ),
        ),
        version="1.0.0",
        tags=("impressora", "fila", "spooler", "impressão"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="printers.status",
                title="Estado das impressoras via PowerShell",
                description="Consulta as classes de impressão do Windows (somente leitura).",
                fn=self._collect_printers,
            )
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return build_demo_printers_status()

    # ------------------------------------------------------------------
    # Coleta
    # ------------------------------------------------------------------
    def _collect_printers(self, ctx: ProbeContext) -> list[CheckResult]:
        include_jobs = bool(ctx.param("include_jobs", True))
        runner = PowerShellRunner()
        try:
            outcome = runner.run_script(
                script_path(_SCRIPT_NAME),
                {"include_jobs": include_jobs},
                timeout_s=ctx.timeout_s,
            )
        except CollectorError as exc:
            return self._all_inconclusive(
                "Não foi possível consultar o estado das impressoras.",
                error_code="POWERSHELL_UNAVAILABLE",
                evidence={"detail": str(exc)[:400]},
            )

        if not outcome.ok:
            return self._all_inconclusive(
                "A coleta do estado das impressoras não produziu dados utilizáveis.",
                error_code="POWERSHELL_FAILED",
                evidence={
                    "stderr": outcome.stderr.strip()[:400],
                    "returncode": outcome.returncode,
                },
            )

        data: dict[str, Any] = outcome.payload
        return [
            self._inventory(data, outcome.duration_ms),
            self._queue(data, outcome.duration_ms),
            self._spooler(data, outcome.duration_ms),
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
    def _inventory(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "printers.inventory")
        if section is None:
            return CheckResult.inconclusive(
                "printers.inventory",
                "Inventário de impressoras",
                "A coleta não retornou o inventário de impressoras.",
                error_code="MISSING_SECTION",
            )
        if section.get("error"):
            return CheckResult.inconclusive(
                "printers.inventory",
                "Inventário de impressoras",
                "Não foi possível obter o inventário de impressoras.",
                error_code="COLLECTION_ERROR",
                evidence={"detail": str(section.get("error"))[:400]},
            )
        if not section.get("available", True):
            return CheckResult.inconclusive(
                "printers.inventory",
                "Inventário de impressoras",
                "O Windows não disponibilizou o inventário de impressoras.",
                error_code="INVENTORY_UNAVAILABLE",
                evidence=section,
            )

        printers = list(section.get("printers") or [])
        if not printers:
            return CheckResult.not_applicable(
                "printers.inventory",
                "Inventário de impressoras",
                "Nenhuma impressora está instalada neste endpoint.",
                evidence=section,
            )

        estados = [classify_printer(printer) for printer in printers]
        falhas = [e for e in estados if e.status is CheckStatus.FAIL]
        avisos = [e for e in estados if e.status is CheckStatus.WARN]
        incertos = [e for e in estados if e.status is CheckStatus.INCONCLUSIVE]

        evidence = {
            "count": len(printers),
            "printers": [
                {
                    **printer,
                    "interpreted": estado.to_dict(),
                }
                for printer, estado in zip(printers, estados)
            ],
            "module_error": section.get("module_error") or "",
        }

        if falhas:
            mensagem = _resumir([f"{e.name}: {e.message}" for e in falhas])
            if avisos:
                mensagem += " | Também em aviso: " + _resumir(
                    [f"{e.name}: {e.message}" for e in avisos]
                )
            return CheckResult.fail(
                "printers.inventory",
                "Inventário de impressoras",
                mensagem,
                severity=Severity.max([e.severity for e in falhas]),
                evidence=evidence,
                remediation=(
                    "Confirmar se o dispositivo está ligado, conectado à rede e "
                    "com a porta correta configurada."
                ),
                duration_ms=duration_ms,
            )

        if avisos:
            return CheckResult.warning(
                "printers.inventory",
                "Inventário de impressoras",
                _resumir([f"{e.name}: {e.message}" for e in avisos]),
                severity=Severity.max([e.severity for e in avisos]),
                evidence=evidence,
                remediation="Confirmar o estado físico e a disponibilidade do dispositivo.",
                duration_ms=duration_ms,
            )

        if incertos and len(incertos) == len(estados):
            return CheckResult.inconclusive(
                "printers.inventory",
                "Inventário de impressoras",
                "O Windows não informou o estado de impressão de nenhum dispositivo.",
                error_code="PRINTER_STATE_UNKNOWN",
                evidence=evidence,
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "printers.inventory",
            "Inventário de impressoras",
            f"{len(printers)} impressora(s) instalada(s), sem erro reportado.",
            evidence=evidence,
            duration_ms=duration_ms,
        )

    def _queue(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "printers.queue")
        if section is None:
            return CheckResult.inconclusive(
                "printers.queue",
                "Fila de impressão",
                "A coleta não retornou a fila de impressão.",
                error_code="MISSING_SECTION",
            )
        if not section.get("included", True):
            return CheckResult.not_applicable(
                "printers.queue",
                "Fila de impressão",
                "A leitura da fila foi desativada pelo operador neste procedimento.",
                evidence=section,
            )
        if section.get("error"):
            return CheckResult.inconclusive(
                "printers.queue",
                "Fila de impressão",
                "Não foi possível ler as filas de impressão.",
                error_code="COLLECTION_ERROR",
                evidence={"detail": str(section.get("error"))[:400]},
            )

        queues = list(section.get("queues") or [])
        impressoras = [q for q in queues if q.get("printer")]
        if not impressoras:
            return CheckResult.not_applicable(
                "printers.queue",
                "Fila de impressão",
                "Não há impressoras instaladas, portanto não há fila a verificar.",
                evidence=section,
            )

        trabalhos: list[dict[str, Any]] = []
        for fila in impressoras:
            for job in fila.get("jobs") or []:
                status, severity, mensagem = classify_job(job)
                trabalhos.append(
                    {
                        "printer": fila.get("printer"),
                        **job,
                        "interpreted": {
                            "status": str(status),
                            "severity": str(severity),
                            "message": mensagem,
                        },
                    }
                )

        evidence = {"queues": queues, "jobs": trabalhos}

        if not trabalhos:
            return CheckResult.ok(
                "printers.queue",
                "Fila de impressão",
                "Nenhum trabalho pendente na fila de impressão.",
                evidence=evidence,
                duration_ms=duration_ms,
            )

        falhas = [
            t
            for t in trabalhos
            if t["interpreted"]["status"] == str(CheckStatus.FAIL)
        ]
        if falhas:
            return CheckResult.fail(
                "printers.queue",
                "Fila de impressão",
                "; ".join(str(t["interpreted"]["message"]) for t in falhas),
                severity=Severity.MEDIUM,
                evidence=evidence,
                remediation=(
                    "Identificar o trabalho com erro e a origem do erro de impressão "
                    "antes de remover o trabalho da fila."
                ),
                duration_ms=duration_ms,
            )

        avisos = [
            t
            for t in trabalhos
            if t["interpreted"]["status"] == str(CheckStatus.WARN)
        ]
        if avisos:
            return CheckResult.warning(
                "printers.queue",
                "Fila de impressão",
                "; ".join(str(t["interpreted"]["message"]) for t in avisos),
                severity=Severity.LOW,
                evidence=evidence,
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "printers.queue",
            "Fila de impressão",
            f"{len(trabalhos)} trabalho(s) na fila, todos em situação normal.",
            evidence=evidence,
            duration_ms=duration_ms,
        )

    def _spooler(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        section = self._section(data, "printers.spooler")
        if section is None:
            return CheckResult.inconclusive(
                "printers.spooler",
                "Serviço de impressão",
                "A coleta não retornou o estado do serviço de impressão.",
                error_code="MISSING_SECTION",
            )
        if not section.get("available"):
            return CheckResult.inconclusive(
                "printers.spooler",
                "Serviço de impressão",
                "Não foi possível consultar o serviço Print Spooler.",
                error_code="SPOOLER_UNAVAILABLE",
                evidence={"detail": str(section.get("error", ""))[:400]},
            )

        status = str(section.get("status", ""))
        if status == "Running":
            return CheckResult.ok(
                "printers.spooler",
                "Serviço de impressão",
                "O serviço Print Spooler está em execução.",
                evidence=section,
                duration_ms=duration_ms,
            )

        return CheckResult.fail(
            "printers.spooler",
            "Serviço de impressão",
            f"O serviço Print Spooler está '{status}'. Causa confirmada de falha de impressão.",
            severity=Severity.HIGH,
            evidence=section,
            remediation=(
                "Verificar o serviço Print Spooler e as políticas que podem impedi "
                "a sua inicialização."
            ),
            duration_ms=duration_ms,
        )
