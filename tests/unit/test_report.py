"""Testes do gerador de relatório técnico.

O foco é garantir que o relatório não diga mais do que os resultados
efetivamente confirmam.
"""

from __future__ import annotations

from deskguard.domain.enums import ExecutionMode
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ProcedureSpec
from deskguard.services.report import build_report_markdown, build_report_text
from deskguard.storage import repository
from deskguard.storage.database import Database


def _spec() -> ProcedureSpec:
    return ProcedureSpec(
        id="teste.relatorio",
        title="Procedimento de teste",
        category="Testes",
        summary="Resumo do procedimento.",
        description="Descrição do procedimento.",
        capability="read_only",
        prerequisites=("Requer permissão de leitura.",),
        risk_notes=("Nenhuma alteração.",),
    )


def _preparar(
    database: Database,
    checks,
    mode=ExecutionMode.LIVE,
    approval=False,
    include_dev_details=True,
):
    with database.session() as session:
        repository.create_execution(
            session,
            execution_id="exec-rel",
            spec=_spec(),
            mode=mode,
            params={"include_account": False},
            actor="teste",
            tool_version="0.1.0",
            host="PC-TESTE",
        )
        row = repository.get_execution(session, "exec-rel")
        row.approval_granted = approval
        repository.finish_execution(
            session,
            "exec-rel",
            status="completed",
            outcome="issues_found",
            checks=checks,
            summary="resumo",
        )

    with database.session() as session:
        row = repository.get_execution(session, "exec-rel")
        steps = repository.get_steps(session, "exec-rel")
        return build_report_markdown(
            row, steps, _spec(), include_dev_details=include_dev_details
        )


def test_relatorio_contem_as_secoes_exigidas(database: Database) -> None:
    markdown = _preparar(
        database,
        [
            CheckResult.ok("c1", "Versão do Windows", "Obtido com sucesso."),
            CheckResult.fail("c2", "Armazenamento", "Volume acima de 95%."),
        ],
    )

    for secao in (
        "## 1. Resumo do problema",
        "## 2. Verificações realizadas",
        "## 3. Procedimentos executados",
        "## 4. Resultados observados",
        "## 5. Solução aplicada",
        "## 6. Pendências e próximos passos",
        "## 7. Confirmações concedidas",
    ):
        assert secao in markdown

    assert "exec-rel" in markdown
    assert "teste.relatorio" in markdown


def test_relatorio_nao_afirma_resolucao(database: Database) -> None:
    markdown = _preparar(
        database,
        [CheckResult.fail("c1", "Serviço parado", "Serviço não está em execução.")],
    )
    assert "Nenhuma alteração foi aplicada ao sistema" in markdown
    assert "Nenhum dos desvios abaixo foi resolvido" in markdown
    assert "resolvido com sucesso" not in markdown


def test_relatorio_descreve_inconclusiva_como_inconclusiva(database: Database) -> None:
    markdown = _preparar(
        database,
        [CheckResult.inconclusive("c1", "Firewall", "Permissão insuficiente.")],
    )
    assert "Inconclusivo" in markdown
    assert "Repetir a coleta com permissão administrativa" in markdown


def test_relatorio_de_execucao_simulada_e_identificado(database: Database) -> None:
    markdown = _preparar(
        database,
        [CheckResult.ok("c1", "Versão", "ok", simulated=True)],
        mode=ExecutionMode.DEMO,
    )
    assert "DADOS SIMULADOS" in markdown
    assert "modo demonstração" in markdown


def test_relatorio_de_execucao_real_declara_origem(database: Database) -> None:
    markdown = _preparar(database, [CheckResult.ok("c1", "Versão", "ok")])
    assert "DADOS REAIS" in markdown


def test_relatorio_marca_ausencia_de_aprovacao(database: Database) -> None:
    markdown = _preparar(database, [CheckResult.ok("c1", "Versão", "ok")])
    assert "Nenhuma confirmação foi concedida" in markdown


def test_relatorio_registra_aprovacao(database: Database) -> None:
    markdown = _preparar(
        database, [CheckResult.ok("c1", "Versão", "ok")], approval=True
    )
    assert "Aprovação explícita concedida" in markdown


def test_relatorio_mostra_tabela_tecnica_e_esconde_json_bruto(
    database: Database,
) -> None:
    markdown = _preparar(
        database,
        [
            CheckResult.ok(
                "printers.inventory",
                "Inventário de impressoras",
                "1 impressora instalada.",
                evidence={
                    "printers": [
                        {
                            "name": "HP LaserJet",
                            "port": "192.168.0.30",
                            "driver": "HP Universal Printing",
                            "printer_status": 1,
                            "detected_error_state": 0,
                            "interpreted": {
                                "state": "ociosa",
                                "status": "pass",
                            },
                        }
                    ],
                    "count": 1,
                },
            )
        ],
    )

    assert "| Nome | Porta | Driver | Status |" in markdown
    assert "| HP LaserJet | 192.168.0.30 | HP Universal Printing | ociosa |" in markdown
    assert "<summary>Dados Brutos (Dev)</summary>" in markdown
    assert '"printer_status"' in markdown


def test_versao_para_copiar_nao_contem_dados_brutos(database: Database) -> None:
    markdown = _preparar(
        database,
        [
            CheckResult.ok(
                "printers.inventory",
                "Inventário de impressoras",
                "1 impressora instalada.",
                evidence={
                    "printers": [
                        {
                            "name": "HP LaserJet",
                            "port": "192.168.0.30",
                            "driver": "HP Universal Printing",
                            "printer_status": 1,
                            "detected_error_state": 0,
                        }
                    ]
                },
            )
        ],
        include_dev_details=False,
    )

    assert "Dados Brutos" not in markdown
    assert '"printer_status"' not in markdown
    assert "| Nome | Porta | Driver | Status |" in markdown
    assert "## 1. Resumo do problema" in markdown


def test_versao_texto_plano_remove_marcacao_markdown(database: Database) -> None:
    markdown = _preparar(database, [CheckResult.ok("c1", "Versão", "ok")])
    texto = build_report_text(markdown)
    assert "##" not in texto
    assert "**" not in texto
    assert "exec-rel" in texto
