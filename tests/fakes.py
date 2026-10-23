"""Procedimentos sintéticos usados apenas pelos testes.

Eles permitem validar o fluxo completo — catálogo, execução, persistência,
relatório e API — sem consultar o sistema operacional do operador.
"""

from __future__ import annotations

from deskguard.catalog.registry import register
from deskguard.collectors.base import Collector, ProbeContext
from deskguard.domain.enums import Capability, PrivilegeLevel
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ParamSpec, ProcedureSpec, StepSpec
from deskguard.procedures.base import Procedure


def _fake_collector(check_id: str, title: str, status_factory=CheckResult.ok):
    def _collect(ctx: ProbeContext) -> CheckResult:
        factor = ctx.param("factor", 1)
        return status_factory(
            check_id,
            title,
            f"Coleta simulada concluída com fator {factor}.",
            evidence={"factor": factor, "simulated": True},
            simulated=True,
        )

    return Collector(check_id=check_id, title=title, fn=_collect)


@register
class FakeReadOnlyProcedure(Procedure):
    """Procedimento somente leitura, com parâmetro numérico validado."""

    spec = ProcedureSpec(
        id="test.fake.readonly",
        title="Procedimento de teste (leitura)",
        category="Testes",
        summary="Procedimento sintético usado para validar o fluxo de execução.",
        description="Não coleta nada do sistema real.",
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=("Nenhum acesso ao sistema real.",),
        params=(
            ParamSpec(
                name="factor",
                label="Fator",
                type="integer",
                default=2,
                min_value=1,
                max_value=10,
            ),
        ),
        steps=(StepSpec(id="fake.check", title="Verificação simulada", description="Sempre aprovada."),),
        version="0.0.1",
    )

    def build_collectors(self) -> list[Collector]:
        return [_fake_collector("fake.check", "Verificação simulada")]

    def build_demo_collectors(self) -> list[Collector]:
        return [_fake_collector("fake.check", "Verificação simulada (demo)")]


@register
class FakeMutatingProcedure(Procedure):
    """Procedimento com capacidade de alteração, usado para testar aprovação."""

    spec = ProcedureSpec(
        id="test.fake.mutating",
        title="Procedimento de teste (alteração)",
        category="Testes",
        summary="Procedimento sintético que exige aprovação explícita.",
        description="Nunca é executado de fato: serve para validar o controle de capacidade.",
        capability=Capability.MODIFYING,
        privilege=PrivilegeLevel.ELEVATED,
        risk_notes=("Alteraria o sistema se fosse executado de verdade.",),
        steps=(StepSpec(id="fake.mutate", title="Alteração simulada", description="Não faz nada."),),
        version="0.0.1",
    )

    def build_collectors(self) -> list[Collector]:
        return [_fake_collector("fake.mutate", "Alteração simulada")]
