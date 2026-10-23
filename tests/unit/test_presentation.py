"""Testes da apresentação em três níveis (resumo, visão técnica e JSON bruto)."""

from __future__ import annotations

from deskguard.services.presentation import (
    build_execution_presentation,
    build_technical_tables,
    section_to_markdown,
)


def _printer_evidence() -> dict:
    return {
        "count": 1,
        "printers": [
            {
                "name": "HP LaserJet",
                "port": "192.168.0.30",
                "driver": "HP Universal Printing",
                "printer_status": 1,
                "detected_error_state": 0,
                "work_offline": False,
                "interpreted": {
                    "state": "ociosa",
                    "status": "pass",
                    "severity": "info",
                },
            }
        ],
    }


def test_impressoras_viram_tabela_com_as_colunas_do_operador() -> None:
    tables = build_technical_tables(_printer_evidence())
    assert len(tables) == 1
    table = tables[0].to_dict()
    assert table["title"] == "Impressoras"
    assert table["columns"] == ["Nome", "Porta", "Driver", "Status"]
    assert table["rows"] == [
        ["HP LaserJet", "192.168.0.30", "HP Universal Printing", "ociosa"]
    ]


def test_evidencia_desconhecida_vira_tabela_campo_valor() -> None:
    tables = build_technical_tables({"factor": 5, "simulated": True})
    assert len(tables) == 1
    table = tables[0].to_dict()
    assert table["title"] == "Informações"
    assert table["rows"] == [["Factor", "5"]]


def test_resumo_conta_os_desfechos() -> None:
    presentation = build_execution_presentation(
        {
            "procedure_title": "Auditoria",
            "outcome": "issues_found",
            "summary": "1 verificação(ões) · 1 desvio(s) confirmado(s)",
            "mode": "live",
        },
        [
            {"check_id": "a", "title": "A", "status": "pass"},
            {"check_id": "b", "title": "B", "status": "fail"},
            {"check_id": "c", "title": "C", "status": "inconclusive"},
        ],
    )
    summary = presentation["summary"]
    assert summary["outcome_label"] == "Desvios confirmados"
    assert summary["counts"]["total"] == 3
    assert summary["counts"]["passed"] == 1
    assert summary["counts"]["confirmed"] == 1
    assert summary["counts"]["inconclusive"] == 1


def test_markdown_da_secao_esconde_o_json_em_bloco_retratil() -> None:
    section = {
        "title": "Inventário de impressoras",
        "status_label": "Aprovado",
        "message": "1 impressora instalada.",
        "tables": [
            build_technical_tables(_printer_evidence())[0].to_dict()
        ],
        "raw_evidence": _printer_evidence(),
        "remediation": "",
    }

    completo = section_to_markdown(section, include_raw=True)
    assert "<details>" in completo
    assert "<summary>Dados Brutos (Dev)</summary>" in completo
    assert '"printer_status"' in completo

    limpo = section_to_markdown(section, include_raw=False)
    assert "Dados Brutos" not in limpo
    assert '"printer_status"' not in limpo
    assert "| Nome | Porta | Driver | Status |" in limpo
