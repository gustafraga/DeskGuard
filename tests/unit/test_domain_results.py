"""Testes do núcleo de domínio: status, severidade e consolidação."""

from __future__ import annotations

from deskguard.domain.enums import CheckStatus, Outcome, Severity
from deskguard.domain.results import CheckResult, aggregate_outcome


def test_pass_nao_e_problema_confirmado() -> None:
    result = CheckResult.ok("c1", "Verificação", "Tudo certo")
    assert result.status is CheckStatus.PASS
    assert not result.is_confirmed_problem
    assert not result.status.is_inconclusive


def test_fail_e_warn_sao_problemas_confirmados() -> None:
    assert CheckResult.fail("c1", "T", "m").is_confirmed_problem
    assert CheckResult.warning("c1", "T", "m").is_confirmed_problem


def test_inconclusiva_nao_e_falha() -> None:
    result = CheckResult.inconclusive("c1", "T", "m", error_code="X")
    assert result.status is CheckStatus.INCONCLUSIVE
    assert not result.is_confirmed_problem
    assert result.status.is_inconclusive


def test_aggregate_prioriza_problema_confirmado() -> None:
    checks = [
        CheckResult.ok("a", "A", "ok"),
        CheckResult.inconclusive("b", "B", "inconclusivo"),
        CheckResult.fail("c", "C", "falha"),
    ]
    assert aggregate_outcome(checks) is Outcome.ISSUES_FOUND


def test_aggregate_sem_problemas_mas_com_inconclusivas() -> None:
    checks = [
        CheckResult.ok("a", "A", "ok"),
        CheckResult.inconclusive("b", "B", "inconclusivo"),
    ]
    assert aggregate_outcome(checks) is Outcome.INCONCLUSIVE


def test_aggregate_saudavel_quando_tudo_passa() -> None:
    checks = [
        CheckResult.ok("a", "A", "ok"),
        CheckResult.not_applicable("b", "B", "n/a"),
        CheckResult.skipped("c", "C", "ignorado"),
    ]
    # "skipped" é inconclusivo, portanto o consolidado não pode ser "saudável".
    assert aggregate_outcome(checks) is Outcome.INCONCLUSIVE

    assert aggregate_outcome([CheckResult.ok("a", "A", "ok")]) is Outcome.HEALTHY


def test_aggregate_sem_verificacoes_e_inconclusivo() -> None:
    assert aggregate_outcome([]) is Outcome.INCONCLUSIVE


def test_severidade_ordena_por_rank() -> None:
    assert Severity.CRITICAL.rank > Severity.HIGH.rank
    assert Severity.HIGH.rank > Severity.MEDIUM.rank
    assert Severity.max([Severity.LOW, Severity.CRITICAL]) is Severity.CRITICAL
    assert Severity.max([]) is Severity.INFO


def test_check_result_preserva_metadados() -> None:
    result = CheckResult.fail(
        "c1",
        "Título",
        "mensagem",
        severity=Severity.HIGH,
        evidence={"a": 1},
        remediation="ação",
        error_code="E42",
    )
    assert result.severity is Severity.HIGH
    assert result.evidence == {"a": 1}
    assert result.remediation == "ação"
    assert result.error_code == "E42"
    assert result.simulated is False
