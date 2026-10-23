"""Gerador de relatório técnico de chamado.

Regras editorial do módulo:

* nunca afirmar que um problema foi resolvido sem confirmação explícita;
* nunca afirmar que um procedimento foi executado sem que ele conste na
  execução registrada;
* descrever inconclusões como inconclusões, e não como aprovação;
* manter todo o texto editável, porque o relatório final édigitado por uma
  pessoa antes de ser anexado ao chamado.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Sequence

from deskguard.domain.enums import CheckStatus, ExecutionMode, Severity
from deskguard.domain.spec import ProcedureSpec
from deskguard.services.presentation import build_step_section, section_to_markdown
from deskguard.storage.models import ExecutionRow, ExecutionStepRow

_STATUS_LABELS: dict[str, str] = {
    str(CheckStatus.PASS): "Aprovado",
    str(CheckStatus.FAIL): "Falha confirmada",
    str(CheckStatus.WARN): "Alerta",
    str(CheckStatus.INCONCLUSIVE): "Inconclusivo",
    str(CheckStatus.NOT_APPLICABLE): "Não aplicável",
    str(CheckStatus.SKIPPED): "Ignorado",
}

_SEVERITY_LABELS: dict[str, str] = {
    str(Severity.INFO): "Informativo",
    str(Severity.LOW): "Baixa",
    str(Severity.MEDIUM): "Média",
    str(Severity.HIGH): "Alta",
    str(Severity.CRITICAL): "Crítica",
}

_MAX_EVIDENCE_CHARS = 400


def _fmt_datetime(value: datetime | None) -> str:
    if value is None:
        return "não registrada"
    return value.strftime("%d/%m/%Y %H:%M:%S %Z").strip() or value.isoformat()


def _fmt_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "não medida"
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    return f"{duration_ms / 1000:.2f} s"


def _fmt_evidence(evidence: Any) -> list[str]:
    """Converte o dicionário de evidências em linhas legíveis."""
    if not isinstance(evidence, dict) or not evidence:
        return []
    lines: list[str] = []
    for key, value in evidence.items():
        if isinstance(value, (dict, list)):
            rendered = _compact(value)
        elif value is None:
            rendered = "não disponível"
        elif isinstance(value, bool):
            rendered = "sim" if value else "não"
        else:
            rendered = str(value)
        if len(rendered) > _MAX_EVIDENCE_CHARS:
            rendered = rendered[:_MAX_EVIDENCE_CHARS] + "…"
        lines.append(f"`{key}`: {rendered}")
    return lines


def _compact(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}={item}" for key, item in value.items())
    return str(value)


def build_report_markdown(
    execution: ExecutionRow,
    steps: Sequence[ExecutionStepRow],
    spec: ProcedureSpec | None = None,
    *,
    include_dev_details: bool = True,
) -> str:
    """Monta o relatório técnico em Markdown.

    ``include_dev_details=False`` gera a versão de circulação: resumo e
    tabelas, sem o bloco retrátil de JSON bruto. É essa versão que o botão
    "Copiar relatório" usa.
    """
    confirmed = [s for s in steps if s.status in (str(CheckStatus.FAIL), str(CheckStatus.WARN))]
    inconclusive = [
        s for s in steps if s.status in (str(CheckStatus.INCONCLUSIVE), str(CheckStatus.SKIPPED))
    ]
    passed = [s for s in steps if s.status == str(CheckStatus.PASS)]
    not_applicable = [s for s in steps if s.status == str(CheckStatus.NOT_APPLICABLE)]

    mode_label = (
        "DADOS REAIS do endpoint (execução ao vivo)"
        if execution.mode == str(ExecutionMode.LIVE)
        else "DADOS SIMULADOS (modo demonstração — não refletir o estado real)"
    )

    lines: list[str] = []
    lines.append(f"# Relatório técnico — {execution.procedure_title}")
    lines.append("")
    lines.append(f"**Identificador da execução:** `{execution.id}`")
    lines.append(f"**Procedimento:** `{execution.procedure_id}` (versão {execution.procedure_version})")
    lines.append(f"**Origem dos dados:** {mode_label}")
    lines.append(f"**Início:** {_fmt_datetime(execution.started_at)}")
    lines.append(f"**Término:** {_fmt_datetime(execution.finished_at)}")
    lines.append(f"**Duração:** {_fmt_duration(execution.duration_ms)}")
    lines.append(f"**Executado por:** {execution.actor}")
    lines.append(f"**Versão da ferramenta:** {execution.tool_version}")
    lines.append("")

    # ------------------------------------------------------------------
    lines.append("## 1. Resumo do problema")
    lines.append("")
    if spec is not None:
        lines.append(spec.summary)
        lines.append("")
        lines.append(
            "Escopo desta execução: coleta de informações de diagnóstico. "
            f"Total de verificações executadas: {len(steps)}."
        )
    else:
        lines.append(execution.summary or "Resumo não disponível para esta execução.")
    lines.append("")
    lines.append(
        f"**Resultado consolidado:** {_outcome_label(execution.outcome)}. "
        f"{len(passed)} verificação(ões) aprovada(s), {len(confirmed)} desvio(s) "
        f"confirmado(s) e {len(inconclusive)} verificação(ões) inconclusiva(s)."
    )
    lines.append("")

    # ------------------------------------------------------------------
    lines.append("## 2. Verificações realizadas")
    lines.append("")
    if steps:
        lines.append("| # | Verificação | Status | Severidade | Duração |")
        lines.append("|---|------------|--------|-----------|---------|")
        for index, step in enumerate(steps, start=1):
            duration = _fmt_duration(step.duration_ms)
            lines.append(
                f"| {index} | {step.title} | {_STATUS_LABELS.get(step.status, step.status)} "
                f"| {_SEVERITY_LABELS.get(step.severity, step.severity)} | {duration} |"
            )
    else:
        lines.append("Nenhuma verificação foi registrada nesta execução.")
    lines.append("")

    # ------------------------------------------------------------------
    lines.append("## 3. Procedimentos executados")
    lines.append("")
    lines.append(
        f"- Procedimento catalogado: `{execution.procedure_id}`"
        + (f" — {spec.title}" if spec else "")
    )
    lines.append(
        f"- Capacidade: {execution.capability} "
        f"({'somente leitura, nenhuma alteração aplicada' if execution.capability == 'read_only' else 'alterações exigem aprovação explícita'})"
    )
    if spec is not None:
        if spec.prerequisites:
            lines.append("- Pré-requisitos declarados:")
            for item in spec.prerequisites:
                lines.append(f"  - {item}")
        if spec.risk_notes:
            lines.append("- Observações de risco:")
            for item in spec.risk_notes:
                lines.append(f"  - {item}")
    lines.append(f"- Parâmetros utilizados: {_fmt_params(execution.params_json)}")
    lines.append("")

    # ------------------------------------------------------------------
    lines.append("## 4. Resultados observados")
    lines.append("")
    if steps:
        for step in steps:
            section = build_step_section(
                {
                    "check_id": step.check_id,
                    "title": step.title,
                    "status": step.status,
                    "severity": step.severity,
                    "message": step.message,
                    "evidence": _loads(step.evidence_json),
                    "remediation": step.remediation,
                    "simulated": step.simulated,
                }
            )
            lines.append(
                section_to_markdown(section, include_raw=include_dev_details)
            )
            if step.error_code:
                lines.append("")
                lines.append(f"- Código de erro: `{step.error_code}`")
            lines.append("")
    else:
        lines.append("Nenhum resultado observado.")
        lines.append("")

    # ------------------------------------------------------------------
    lines.append("## 5. Solução aplicada")
    lines.append("")
    if execution.capability == "read_only":
        lines.append(
            "**Nenhuma alteração foi aplicada ao sistema.** Este procedimento é "
            "exclusivamente de leitura e serve para levantar evidências."
        )
    else:
        lines.append(
            "Esta execução possuía capacidade de alteração. Consulte a trilha de "
            "auditoria para o registro de confirmações concedidas."
        )
    if confirmed:
        lines.append("")
        lines.append(
            "Nenhum dos desvios abaixo foi resolvido por esta execução: as etapas "
            "de correção são manuais ou pertencem a procedimentos distintos."
        )
    lines.append("")

    # ------------------------------------------------------------------
    lines.append("## 6. Pendências e próximos passos")
    lines.append("")
    pendencias: list[str] = []
    for step in confirmed:
        remediation = step.remediation or "Avaliar com o suporte e definir a ação corretiva."
        pendencias.append(
            f"**{step.title}** ({_SEVERITY_LABELS.get(step.severity, step.severity)}): "
            f"{step.message} — {remediation}"
        )
    for step in inconclusive:
        pendencias.append(
            f"**{step.title}** (inconclusivo): {step.message} "
            "Repetir a coleta com permissão administrativa ou com o componente indisponível resolvido."
        )
    if not_applicable:
        pendencias.append(
            "Verificações marcadas como não aplicáveis: "
            + ", ".join(step.title for step in not_applicable)
            + "."
        )
    if pendencias:
        for item in pendencias:
            lines.append(f"- {item}")
    else:
        lines.append(
            "Nenhuma pendência identificada pelas verificações executadas. "
            "Recomenda-se registrar o resultado no chamado e aguardar novos sintomas."
        )
    lines.append("")

    # ------------------------------------------------------------------
    lines.append("## 7. Confirmações concedidas")
    lines.append("")
    if execution.approval_granted:
        lines.append(
            "Aprovação explícita concedida para esta execução. Consulte a trilha "
            "de auditoria para detalhes."
        )
    else:
        lines.append(
            "Nenhuma confirmação foi concedida. Nenhuma ação que modifique o "
            "sistema foi executada nesta execução."
        )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "*Relatório gerado automaticamente pelo DeskGuard. O texto é editável e "
        "deve ser revisado antes do uso em um chamado. Este documento reflete "
        "apenas as verificações implementadas e efetivamente executadas; a "
        "aprovação dessas verificações não equivale a uma certificação de que o "
        "equipamento esteja livre de problemas.*"
    )
    lines.append("")

    return "\n".join(lines)


def build_report_text(markdown: str) -> str:
    """Converte o Markdown em texto simples, para exportação `.txt`."""
    text = markdown
    # Do prefixo mais longo para o mais curto: caso contrário, "# " consumiria
    # parte de "## " e deixaria marcadores residuais.
    for marker in ("#### ", "### ", "## ", "# "):
        text = text.replace(marker, "")
    text = text.replace("**", "").replace("`", "").replace("|", " ")
    return text


def _outcome_label(outcome: str) -> str:
    return {
        "healthy": "sem desvios confirmados",
        "issues_found": "desvios confirmados",
        "inconclusive": "inconclusivo",
        "error": "erro na execução",
    }.get(outcome, outcome)


def _fmt_params(raw_params_json: str | None) -> str:
    from deskguard.storage.models import loads_json

    params = loads_json(raw_params_json)
    if not isinstance(params, dict) or not params:
        return "nenhum"
    return ", ".join(f"`{key}`={value}" for key, value in sorted(params.items()))


def _loads(raw: str | None) -> Any:
    from deskguard.storage.models import loads_json

    return loads_json(raw)


def summarize_for_list(steps: Iterable[ExecutionStepRow]) -> list[dict[str, Any]]:
    """Lista compacta das etapas, usada em visões resumidas."""
    return [
        {
            "title": step.title,
            "status": step.status,
            "severity": step.severity,
        }
        for step in steps
    ]
