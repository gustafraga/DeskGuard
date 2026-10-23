"""Testes do motor de coletores: tratamento de erro, dependências e duração."""

from __future__ import annotations

from deskguard.collectors.base import Collector, ProbeContext, run_collectors
from deskguard.domain.enums import CheckStatus, ExecutionMode
from deskguard.domain.results import CheckResult


def _ctx() -> ProbeContext:
    return ProbeContext(
        execution_id="exec-teste",
        mode=ExecutionMode.LIVE,
        timeout_s=5.0,
        params={},
    )


def test_excecao_vira_inconclusiva_e_nao_falha() -> None:
    def _boom(ctx: ProbeContext) -> CheckResult:
        raise RuntimeError("falha interna")

    collectors = [Collector(check_id="c1", title="Coleta", fn=_boom)]
    results = run_collectors(collectors, _ctx())

    assert len(results) == 1
    assert results[0].status is CheckStatus.INCONCLUSIVE
    assert results[0].error_code == "COLLECTOR_ERROR"
    assert not results[0].is_confirmed_problem


def test_dependencia_nao_satisfeita_dispara_skip() -> None:
    def _falha(ctx: ProbeContext) -> CheckResult:
        return CheckResult.fail("c1", "Primeira", "problema confirmado")

    def _dependente(ctx: ProbeContext) -> CheckResult:
        raise AssertionError("não deveria ser executado")

    collectors = [
        Collector(check_id="c1", title="Primeira", fn=_falha),
        Collector(
            check_id="c2",
            title="Dependente",
            fn=_dependente,
            depends_on=("c1",),
        ),
    ]
    results = run_collectors(collectors, _ctx())

    assert results[0].status is CheckStatus.FAIL
    assert results[1].status is CheckStatus.SKIPPED
    assert results[1].evidence["blocked_by"] == ["c1"]


def test_coletor_multiplo_e_expandido() -> None:
    def _varios(ctx: ProbeContext) -> list[CheckResult]:
        return [
            CheckResult.ok("a", "A", "ok"),
            CheckResult.ok("b", "B", "ok"),
        ]

    results = run_collectors([Collector(check_id="a", title="A", fn=_varios)], _ctx())
    assert [r.check_id for r in results] == ["a", "b"]


def test_duracao_e_preenchida_quando_ausente() -> None:
    results = run_collectors(
        [Collector(check_id="a", title="A", fn=lambda ctx: CheckResult.ok("a", "A", "ok"))],
        _ctx(),
    )
    assert results[0].duration_ms is not None
    assert results[0].duration_ms >= 0


def test_inconclusiva_nao_bloqueia_dependentes() -> None:
    def _inconclusiva(ctx: ProbeContext) -> CheckResult:
        return CheckResult.inconclusive("c1", "Primeira", "sem permissão")

    def _dependente(ctx: ProbeContext) -> CheckResult:
        return CheckResult.ok("c2", "Dependente", "ok")

    collectors = [
        Collector(check_id="c1", title="Primeira", fn=_inconclusiva),
        Collector(check_id="c2", title="Dependente", fn=_dependente, depends_on=("c1",)),
    ]
    results = run_collectors(collectors, _ctx())
    assert results[1].status is CheckStatus.PASS
