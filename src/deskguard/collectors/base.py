"""Contratos da camada de coleta.

A camada de coleta é a única parte do DeskGuard que fala com o sistema
operacional. Todo acesso é somente leitura e toda falha de coleta precisa
resultar em uma verificação *inconclusiva*, nunca em uma falha confirmada.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from deskguard.domain.enums import CheckStatus, ExecutionMode
from deskguard.domain.results import CheckResult


@dataclass(slots=True)
class ProbeContext:
    """Contexto entregue a cada coletor durante uma execução."""

    execution_id: str
    mode: ExecutionMode
    timeout_s: float
    params: Mapping[str, Any] = field(default_factory=dict)
    shared: dict[str, Any] = field(default_factory=dict)

    def param(self, name: str, default: Any = None) -> Any:
        return self.params.get(name, default)


@dataclass(frozen=True, slots=True)
class Collector:
    """Uma verificação executável, com identidade e dependências declaradas."""

    check_id: str
    title: str
    fn: Callable[[ProbeContext], CheckResult | list[CheckResult]]
    description: str = ""
    depends_on: tuple[str, ...] = ()

    def run(self, ctx: ProbeContext) -> CheckResult | list[CheckResult]:
        return self.fn(ctx)


def run_collectors(
    collectors: Sequence[Collector], ctx: ProbeContext
) -> list[CheckResult]:
    """Executa os coletores em ordem, tratando erros e dependências.

    Regras de segurança e de qualidade:
      * uma exceção vira `INCONCLUSIVE`, nunca `FAIL`;
      * um coletor cujo pré-requisito falhou é marcado como `SKIPPED`;
      * a ordem de execução é preservada para que o relatório seja estável.
    """
    results: list[CheckResult] = []
    blocked: set[str] = set()

    for collector in collectors:
        unmet = [dep for dep in collector.depends_on if dep in blocked]
        if unmet:
            result = CheckResult.skipped(
                collector.check_id,
                collector.title,
                f"Pré-requisito não satisfeito: {', '.join(unmet)}.",
                evidence={"blocked_by": unmet},
            )
            blocked.add(collector.check_id)
            results.append(result)
            continue

        started = time.perf_counter()
        try:
            produced = collector.run(ctx)
        except Exception as exc:  # noqa: BLE001 - fronteira de isolamento
            duration_ms = int((time.perf_counter() - started) * 1000)
            result = CheckResult.inconclusive(
                collector.check_id,
                collector.title,
                "A verificação não pôde ser concluída por erro interno do coletor.",
                error_code="COLLECTOR_ERROR",
                evidence={
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc)[:400],
                },
                duration_ms=duration_ms,
            )
            blocked.add(collector.check_id)
            results.append(result)
            continue

        produced_list = produced if isinstance(produced, list) else [produced]
        for item in produced_list:
            if item.duration_ms is None:
                elapsed = int((time.perf_counter() - started) * 1000)
                item = _with_duration(item, elapsed)
            results.append(item)
            if item.status in (CheckStatus.FAIL, CheckStatus.SKIPPED):
                blocked.add(item.check_id)

    return results


def _with_duration(result: CheckResult, duration_ms: int) -> CheckResult:
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
