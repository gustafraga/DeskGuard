"""Testes da persistência local e dos indicadores do painel."""

from __future__ import annotations

from deskguard.domain.enums import ExecutionMode
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ProcedureSpec
from deskguard.storage import repository
from deskguard.storage.database import Database


def _spec() -> ProcedureSpec:
    return ProcedureSpec(
        id="teste.execucao",
        title="Procedimento de teste",
        category="Testes",
        summary="Resumo de teste",
        description="",
    )


def test_ciclo_de_vida_de_uma_execucao(database: Database) -> None:
    with database.session() as session:
        repository.create_execution(
            session,
            execution_id="exec-1",
            spec=_spec(),
            mode=ExecutionMode.LIVE,
            params={"fator": 2},
            actor="teste",
            tool_version="0.1.0",
            host="PC-TESTE",
        )
        repository.mark_running(session, "exec-1", repository.utcnow())

    checks = [
        CheckResult.ok("c1", "Aprovada", "ok", evidence={"x": 1}),
        CheckResult.fail("c2", "Com falha", "problema", severity="high"),
        CheckResult.inconclusive("c3", "Inconclusiva", "sem permissão"),
    ]

    with database.session() as session:
        repository.finish_execution(
            session,
            "exec-1",
            status="completed",
            outcome="issues_found",
            checks=checks,
            summary="resumo",
        )

    with database.session() as session:
        row = repository.get_execution(session, "exec-1")
        steps = repository.get_steps(session, "exec-1")

        assert row is not None
        assert row.status == "completed"
        assert row.outcome == "issues_found"
        assert row.duration_ms is not None and row.duration_ms >= 0
        assert row.summary == "resumo"
        assert len(steps) == 3
        assert steps[1].status == "fail"
        assert steps[1].severity == "high"


def test_busca_no_historico_filtra_por_texto(database: Database) -> None:
    with database.session() as session:
        repository.create_execution(
            session,
            execution_id="exec-a",
            spec=_spec(),
            mode=ExecutionMode.LIVE,
            params={},
        )
        repository.finish_execution(
            session,
            "exec-a",
            status="completed",
            outcome="healthy",
            checks=[CheckResult.ok("c1", "A", "ok")],
            summary="tudo certo",
        )
        repository.create_execution(
            session,
            execution_id="exec-b",
            spec=_spec(),
            mode=ExecutionMode.DEMO,
            params={},
        )
        repository.finish_execution(
            session,
            "exec-b",
            status="completed",
            outcome="healthy",
            checks=[CheckResult.ok("c1", "A", "ok")],
            summary="simulado",
        )

    with database.session() as session:
        assert len(repository.list_executions(session)) == 2
        assert len(repository.list_executions(session, query="tudo certo")) == 1
        assert len(repository.list_executions(session, mode="demo")) == 1
        assert repository.count_executions(session, query="simulado") == 1


def test_trilha_de_auditoria_registra_acoes(database: Database) -> None:
    with database.session() as session:
        repository.record_audit(
            session,
            action="execution.started",
            actor="teste",
            target="teste.execucao",
            outcome="accepted",
            mode=ExecutionMode.LIVE,
            execution_id="exec-1",
            approval_granted=False,
            details={"parametros": 1},
        )

    with database.session() as session:
        eventos = repository.list_audit(session)
        assert len(eventos) == 1
        assert eventos[0].action == "execution.started"
        assert eventos[0].details_json


def test_indicadores_do_painel_sao_calculados_dos_dados(database: Database) -> None:
    with database.session() as session:
        repository.create_execution(
            session,
            execution_id="exec-1",
            spec=_spec(),
            mode=ExecutionMode.LIVE,
            params={},
        )
        repository.finish_execution(
            session,
            "exec-1",
            status="completed",
            outcome="issues_found",
            checks=[
                CheckResult.ok("c1", "A", "ok"),
                CheckResult.fail("c2", "B", "problema", severity="critical"),
            ],
            summary="resumo",
        )

    with database.session() as session:
        stats = repository.dashboard_stats(session)

    assert stats["total_executions"] == 1
    assert stats["executions_24h"] == 1
    assert stats["confirmed_issues"] == 1
    assert stats["inconclusive_checks"] == 0
    assert stats["by_outcome"].get("issues_found") == 1
    assert stats["by_severity"].get("critical") == 1
    assert stats["max_severity"] == "critical"
    assert stats["last_execution_at"] is not None


def test_resumo_de_verificacoes_descreve_desvios_e_inconclusivas() -> None:
    resumo = repository.summarize_checks(
        [
            CheckResult.ok("a", "A", "ok"),
            CheckResult.fail("b", "B", "falha"),
            CheckResult.inconclusive("c", "C", "inconclusiva"),
        ]
    )
    assert "1 desvio(s) confirmado(s)" in resumo
    assert "1 inconclusiva(s)" in resumo
    assert repository.summarize_checks([]) == "Nenhuma verificação executada."
