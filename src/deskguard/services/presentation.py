"""Apresentação em três níveis dos resultados de uma execução.

A mesma execução é mostrada em três camadas, para não misturar públicos:

* **N1 — Resumo**: texto curto, com o desfecho e a contagem de verificações.
* **N2/N3 — Visão técnica**: tabelas legíveis montadas a partir das
  evidências coletadas (impressoras, serviços, firewall, rede, disco...).
* **Dev — Dados brutos**: o JSON original, disponível apenas dentro de um
  bloco retrátil ``Dados Brutos`` e nunca misturado ao relatório principal.

As tabelas são derivadas das evidências por reconhecedores conhecidos. O que
não tem um formato específico cai em uma tabela genérica de campo/valor, de
modo que nenhuma evidência fica de fora — e nenhuma delas precisa ser exibida
como JSON para o operador de N1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from deskguard.collectors.printer_status import classify_printer
from deskguard.domain.enums import CheckStatus, Severity

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

_OUTCOME_LABELS: dict[str, str] = {
    "healthy": "Sem desvios confirmados",
    "issues_found": "Desvios confirmados",
    "inconclusive": "Inconclusivo",
    "error": "Erro na execução",
}

# Chaves de controle que não são dados de interesse para a visão técnica.
_NOISE_KEYS = {
    "simulated",
    "notice",
    "available",
    "included",
    "count",
    "error",
    "module_error",
    "products_error",
    "product_count",
    "not_applicable",
    "passed",
    "inconclusive",
    "confirmed_problems",
    "broken_dependencies",
    "stopped_with_impact",
    "rejected_targets",
}

_TITLES: dict[str, str] = {
    "printers": "Impressoras",
    "queues": "Fila de impressão",
    "jobs": "Trabalhos de impressão",
    "services": "Serviços",
    "findings": "Achados de segurança",
    "adapters": "Adaptadores",
    "configs": "Endereçamento IP",
    "default_routes": "Rotas padrão",
    "profiles": "Perfis de rede",
    "results": "Destinos testados",
    "volumes": "Volumes",
    "dependencies": "Dependências",
    "products": "Produtos de segurança registrados",
    "monitored": "Serviços monitorados",
    "context": "Contexto",
    "allowlist": "Destinos autorizados",
    "defender": "Windows Defender",
    "uac": "UAC (Controle de Conta de Usuário)",
    "screen_lock": "Bloqueio de tela",
    "remote_desktop": "Área de Trabalho Remota",
    "encryption": "Criptografia do disco",
    "guest_account": "Conta de convidado",
    "caption": "Descrição",
    "security": "Segurança",
}

_COLUMNS: dict[str, str] = {
    "name": "Nome",
    "display_name": "Nome",
    "label": "Item",
    "port": "Porta",
    "driver": "Driver",
    "status": "Situação",
    "state": "Situação",
    "start_type": "Inicialização",
    "severity_label": "Severidade",
    "severity": "Severidade",
    "message": "Observação",
    "host": "Destino",
    "source": "Origem",
    "address": "Endereço",
    "addresses": "Endereços",
    "gateway": "Gateway",
    "gateways": "Gateway",
    "dns_servers": "DNS",
    "next_hop": "Próximo salto",
    "interface": "Interface",
    "destination": "Destino",
    "category": "Categoria",
    "ipv4_state": "IPv4",
    "ipv6_state": "IPv6",
    "path": "Caminho",
    "total_gb": "Total (GB)",
    "free_gb": "Livre (GB)",
    "used_percent": "Uso (%)",
    "printer": "Impressora",
    "document": "Documento",
    "user": "Usuário",
    "job_status": "Situação",
    "job_status_text": "Situação",
    "depends_on": "Depende de",
    "dependents": "Dependentes",
    "media_type": "Tipo de mídia",
    "mac_address": "Endereço MAC",
    "registered_at": "Registrado em",
    "product_state": "Estado bruto",
}

# Limite de colunas em tabelas genéricas: evita transformar evidências
# inesperadas em uma parede horizontal de campos técnicos.
_MAX_GENERIC_COLUMNS = 8


@dataclass(frozen=True, slots=True)
class TechnicalTable:
    """Tabela pronta para ser renderizada na interface ou em Markdown."""

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
        }


def status_label(status: str | None) -> str:
    return _STATUS_LABELS.get(str(status), str(status or "—"))


def severity_label(severity: str | None) -> str:
    return _SEVERITY_LABELS.get(str(severity), str(severity or "—"))


def outcome_label(outcome: str | None) -> str:
    return _OUTCOME_LABELS.get(str(outcome), str(outcome or "—"))


def _text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, (list, tuple, set)):
        if not value:
            return "—"
        return ", ".join(_text(item) for item in value)
    if isinstance(value, Mapping):
        if not value:
            return "—"
        return "; ".join(f"{key}: {_text(item)}" for key, item in value.items())
    rendered = str(value).strip()
    return rendered or "—"


def _column_label(key: str) -> str:
    return _COLUMNS.get(key, key.replace("_", " ").strip().capitalize())


def _title_for(key: str) -> str:
    return _TITLES.get(key, key.replace("_", " ").strip().capitalize())


def _build_table(
    title: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> TechnicalTable | None:
    normalized: list[tuple[str, ...]] = []
    for row in rows:
        cells = tuple(_text(cell) for cell in row)
        if all(cell in ("", "—") for cell in cells):
            continue
        normalized.append(cells)
    if not normalized:
        return None
    return TechnicalTable(title=title, columns=tuple(columns), rows=tuple(normalized))


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


# --------------------------------------------------------------------------
# Reconhecedores específicos
# --------------------------------------------------------------------------
def _printers_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = []
    for printer in items:
        interpreted = printer.get("interpreted")
        if isinstance(interpreted, dict):
            state = interpreted.get("state")
        else:
            try:
                state = classify_printer(printer).state
            except (TypeError, ValueError, KeyError):
                state = None
        rows.append(
            [
                printer.get("name"),
                printer.get("port"),
                printer.get("driver"),
                state or _column_label("status"),
            ]
        )
    return _build_table(
        "Impressoras", ("Nome", "Porta", "Driver", "Status"), rows
    )


def _queues_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = []
    has_jobs = any(item.get("jobs") for item in items)
    if has_jobs:
        for queue in items:
            for job in queue.get("jobs") or []:
                if not isinstance(job, dict):
                    continue
                interpreted = job.get("interpreted")
                if isinstance(interpreted, dict):
                    situation = interpreted.get("message") or interpreted.get("status")
                else:
                    situation = job.get("job_status_text") or job.get("job_status")
                rows.append(
                    [
                        queue.get("printer"),
                        job.get("document"),
                        job.get("user"),
                        situation,
                    ]
                )
        return _build_table(
            "Fila de impressão",
            ("Impressora", "Documento", "Usuário", "Situação"),
            rows,
        )

    for queue in items:
        rows.append([queue.get("printer"), queue.get("count")])
    return _build_table(
        "Filas de impressão", ("Impressora", "Trabalhos"), rows
    )


def _jobs_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = []
    for job in items:
        interpreted = job.get("interpreted")
        if isinstance(interpreted, dict):
            situation = interpreted.get("message") or interpreted.get("status")
        else:
            situation = job.get("job_status_text") or job.get("job_status")
        rows.append(
            [
                job.get("printer"),
                job.get("document"),
                job.get("user"),
                situation,
            ]
        )
    return _build_table(
        "Trabalhos de impressão",
        ("Impressora", "Documento", "Usuário", "Situação"),
        rows,
    )


def _services_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = [
        [
            service.get("display_name") or service.get("name"),
            service.get("status"),
            service.get("start_type"),
        ]
        for service in items
    ]
    return _build_table(
        "Serviços", ("Serviço", "Situação", "Inicialização"), rows
    )


def _findings_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = [
        [
            finding.get("label") or finding.get("key"),
            status_label(finding.get("status")),
            finding.get("severity_label") or severity_label(finding.get("severity")),
            finding.get("message"),
        ]
        for finding in items
    ]
    return _build_table(
        "Achados de segurança",
        ("Item", "Situação", "Severidade", "Observação"),
        rows,
    )


def _adapters_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = [
        [
            adapter.get("name"),
            adapter.get("status"),
            adapter.get("media_type"),
            adapter.get("mac_address"),
        ]
        for adapter in items
    ]
    return _build_table(
        "Adaptadores",
        ("Nome", "Situação", "Tipo de mídia", "Endereço MAC"),
        rows,
    )


def _configs_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = []
    for config in items:
        addresses = [
            address.get("address")
            for address in (config.get("addresses") or [])
            if isinstance(address, dict)
            and str(address.get("state")) == "Preferred"
        ]
        gateways = [
            gateway.get("next_hop")
            for gateway in (config.get("gateways") or [])
            if isinstance(gateway, dict)
        ]
        rows.append(
            [
                config.get("interface"),
                addresses,
                gateways,
                config.get("dns_servers"),
            ]
        )
    return _build_table(
        "Endereçamento IP",
        ("Interface", "Endereços", "Gateway", "DNS"),
        rows,
    )


def _routes_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = [
        [
            route.get("destination"),
            route.get("next_hop"),
            route.get("interface"),
        ]
        for route in items
    ]
    return _build_table(
        "Rotas padrão", ("Destino", "Próximo salto", "Interface"), rows
    )


def _profiles_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = [
        [
            profile.get("interface"),
            profile.get("name"),
            profile.get("category"),
            profile.get("ipv4_state"),
            profile.get("ipv6_state"),
        ]
        for profile in items
    ]
    return _build_table(
        "Perfis de rede",
        ("Interface", "Nome", "Categoria", "IPv4", "IPv6"),
        rows,
    )


def _network_results_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    if not any(
        "dns" in item or "icmp" in item or "tcp" in item or "ports" in item
        for item in items
    ):
        return None

    rows = []
    for item in items:
        dns = item.get("dns") if isinstance(item.get("dns"), dict) else {}
        icmp = item.get("icmp") if isinstance(item.get("icmp"), dict) else {}
        tcp = item.get("tcp") if isinstance(item.get("tcp"), list) else item.get("ports")
        tcp = tcp if isinstance(tcp, list) else []

        if dns:
            dns_text = (
                dns.get("addresses")
                or ("resolvido" if dns.get("resolved") else dns.get("error") or "não resolvido")
            )
        else:
            dns_text = "—"

        if icmp:
            if icmp.get("reachable"):
                rtt = icmp.get("rtt_ms")
                icmp_text = f"respondeu ({rtt} ms)" if rtt is not None else "respondeu"
            else:
                icmp_text = icmp.get("error") or icmp.get("status") or "sem resposta"
        elif "reachable" in item:
            rtt = item.get("rtt_ms")
            icmp_text = (
                f"respondeu ({rtt} ms)" if item.get("reachable") and rtt is not None
                else "respondeu" if item.get("reachable")
                else item.get("error") or item.get("status") or "sem resposta"
            )
        else:
            icmp_text = "—"

        if tcp:
            tcp_text = ", ".join(
                f"{porta.get('port')}: {porta.get('state')}"
                for porta in tcp
                if isinstance(porta, dict)
            )
        else:
            tcp_text = "—"

        rows.append([item.get("host"), dns_text, icmp_text, tcp_text])

    return _build_table(
        "Destinos testados", ("Destino", "DNS", "ICMP", "TCP"), rows
    )


def _volumes_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = [
        [
            volume.get("path"),
            volume.get("total_gb"),
            volume.get("free_gb"),
            volume.get("used_percent"),
        ]
        for volume in items
    ]
    return _build_table(
        "Volumes",
        ("Caminho", "Total (GB)", "Livre (GB)", "Uso (%)"),
        rows,
    )


def _dependencies_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    if not any("depends_on" in item or "dependents" in item for item in items):
        return None
    rows = [
        [
            item.get("name"),
            item.get("depends_on"),
            item.get("dependents"),
        ]
        for item in items
    ]
    return _build_table(
        "Dependências",
        ("Serviço", "Depende de", "Dependentes"),
        rows,
    )


def _products_table(items: list[dict[str, Any]]) -> TechnicalTable | None:
    rows = [[item.get("name"), item.get("registered_at")] for item in items]
    return _build_table(
        "Produtos de segurança registrados",
        ("Produto", "Registrado em"),
        rows,
    )


_SPECIAL_TABLES = (
    ("printers", _printers_table),
    ("queues", _queues_table),
    ("jobs", _jobs_table),
    ("services", _services_table),
    ("findings", _findings_table),
    ("adapters", _adapters_table),
    ("configs", _configs_table),
    ("default_routes", _routes_table),
    ("profiles", _profiles_table),
    ("results", _network_results_table),
    ("volumes", _volumes_table),
    ("dependencies", _dependencies_table),
    ("products", _products_table),
)


# --------------------------------------------------------------------------
# Reconhecedor genérico
# --------------------------------------------------------------------------
def _generic_dict_table(key: str, value: Mapping[str, Any]) -> TechnicalTable | None:
    rows = []
    for field, item in value.items():
        if field in _NOISE_KEYS or item in (None, "", [], {}):
            continue
        rows.append([_column_label(field), item])
    return _build_table(_title_for(key), ("Campo", "Valor"), rows)


def _generic_list_table(key: str, value: list[Any]) -> TechnicalTable | None:
    dict_items = [item for item in value if isinstance(item, dict)]
    if dict_items:
        fields: list[str] = []
        for item in dict_items:
            for field in item:
                if field in _NOISE_KEYS or field in fields:
                    continue
                fields.append(field)
        fields = fields[:_MAX_GENERIC_COLUMNS]
        rows = [[item.get(field) for field in fields] for item in dict_items]
        return _build_table(
            _title_for(key),
            [_column_label(field) for field in fields],
            rows,
        )

    scalars = [item for item in value if not isinstance(item, (dict, list))]
    if scalars:
        return _build_table(_title_for(key), ("Valor",), [[item] for item in scalars])
    return None


def build_technical_tables(evidence: Any) -> list[TechnicalTable]:
    """Converte um dicionário de evidências em tabelas legíveis."""
    if not isinstance(evidence, Mapping) or not evidence:
        return []

    tables: list[TechnicalTable] = []
    consumed: set[str] = set()

    for key, recognizer in _SPECIAL_TABLES:
        if key not in evidence:
            continue
        value = evidence.get(key)
        if isinstance(value, list) and value:
            table = recognizer(_dicts(value))
            if table is not None:
                tables.append(table)
        if isinstance(value, list):
            consumed.add(key)

    scalar_rows: list[tuple[str, Any]] = []
    for key, value in evidence.items():
        if key in consumed or key in _NOISE_KEYS or value in (None, "", [], {}):
            continue
        if isinstance(value, Mapping):
            table = _generic_dict_table(key, value)
            if table is not None:
                tables.append(table)
        elif isinstance(value, list):
            table = _generic_list_table(key, value)
            if table is not None:
                tables.append(table)
        else:
            scalar_rows.append((_column_label(key), value))

    if scalar_rows:
        table = _build_table("Informações", ("Campo", "Valor"), scalar_rows)
        if table is not None:
            tables.append(table)

    return tables


# --------------------------------------------------------------------------
# Seções e resumo
# --------------------------------------------------------------------------
def build_step_section(step: Mapping[str, Any]) -> dict[str, Any]:
    """Monta a visão N2/N3 de uma etapa, com as evidências brutas à parte."""
    evidence = step.get("evidence") or {}
    return {
        "check_id": step.get("check_id"),
        "title": step.get("title") or step.get("check_id") or "Verificação",
        "status": step.get("status"),
        "status_label": status_label(step.get("status")),
        "severity": step.get("severity"),
        "severity_label": severity_label(step.get("severity")),
        "message": step.get("message") or "",
        "remediation": step.get("remediation") or "",
        "simulated": bool(step.get("simulated")),
        "tables": [table.to_dict() for table in build_technical_tables(evidence)],
        "raw_evidence": evidence if isinstance(evidence, Mapping) else {},
    }


def build_execution_presentation(
    execution: Mapping[str, Any],
    steps: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resumo N1 e seções técnicas de uma execução já persistida."""
    counts = {
        "total": len(steps),
        "passed": sum(1 for step in steps if step.get("status") == str(CheckStatus.PASS)),
        "confirmed": sum(
            1
            for step in steps
            if step.get("status") in (str(CheckStatus.FAIL), str(CheckStatus.WARN))
        ),
        "inconclusive": sum(
            1
            for step in steps
            if step.get("status")
            in (str(CheckStatus.INCONCLUSIVE), str(CheckStatus.SKIPPED))
        ),
        "not_applicable": sum(
            1 for step in steps if step.get("status") == str(CheckStatus.NOT_APPLICABLE)
        ),
    }
    return {
        "summary": {
            "title": execution.get("procedure_title") or execution.get("procedure_id"),
            "outcome": execution.get("outcome"),
            "outcome_label": outcome_label(execution.get("outcome")),
            "text": execution.get("summary") or "Resumo não disponível.",
            "mode": execution.get("mode"),
            "counts": counts,
        },
        "sections": [build_step_section(step) for step in steps],
    }


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def _md_cell(value: Any) -> str:
    text = _text(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def table_to_markdown(table: Mapping[str, Any]) -> str:
    columns = [str(column) for column in table.get("columns") or []]
    if not columns:
        return ""
    lines = [
        "| " + " | ".join(_md_cell(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in table.get("rows") or []:
        cells = [_md_cell(cell) for cell in row]
        cells += [""] * (len(columns) - len(cells))
        lines.append("| " + " | ".join(cells[: len(columns)]) + " |")
    return "\n".join(lines)


def raw_evidence_block(evidence: Mapping[str, Any]) -> str:
    payload = json.dumps(evidence, ensure_ascii=False, indent=2, default=str)
    return "\n".join(
        [
            "<details>",
            "<summary>Dados Brutos (Dev)</summary>",
            "",
            "```json",
            payload,
            "```",
            "",
            "</details>",
        ]
    )


def section_to_markdown(
    section: Mapping[str, Any], *, include_raw: bool = True
) -> str:
    """Renderiza uma seção técnica em Markdown, com o JSON sob demanda."""
    lines: list[str] = [
        f"### {section.get('title')} — {section.get('status_label')}",
        "",
    ]
    message = str(section.get("message") or "").strip()
    if message:
        lines.append(message)
        lines.append("")

    tables = list(section.get("tables") or [])
    if tables:
        lines.append("**Visão técnica**")
        lines.append("")
        for table in tables:
            lines.append(f"**{table.get('title')}**")
            lines.append("")
            rendered = table_to_markdown(table)
            if rendered:
                lines.append(rendered)
                lines.append("")
    else:
        lines.append(
            "_Nenhum dado tabular foi registrado para esta verificação._"
        )
        lines.append("")

    remediation = str(section.get("remediation") or "").strip()
    if remediation:
        lines.append(f"**Recomendação:** {remediation}")
        lines.append("")

    raw = section.get("raw_evidence")
    if include_raw and isinstance(raw, Mapping) and raw:
        lines.append(raw_evidence_block(raw))
        lines.append("")

    return "\n".join(lines).rstrip()
