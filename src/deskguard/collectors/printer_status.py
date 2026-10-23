"""Tradução dos códigos de estado do Windows para o vocabulário do DeskGuard.

O Windows expõe o estado de uma impressora por três campos numéricos
(`PrinterStatus`, `DetectedErrorState` e `ExtendedPrinterStatus`) e o estado
da fila por `JobStatus`. Este módulo converte esses códigos em um estado
legível e em um `CheckStatus`.

`JobStatus` é uma máscara de bits (1 = pausado, 2 = erro, 32 = offline,
64 = sem papel, 4096 = concluído, ...) e por isso é decodificado por bit,
nunca por igualdade com o valor numérico.

Princípio aplicado: **só é considerada falha confirmada o que o dispositivo
reportou explicitamente**. Indicadores ambíguos — como ``PrinterStatus = 3``
("offline"), que o Windows também devolve para impressoras virtuais ociosas —
não viram falha; eles viram aviso de severidade baixa ou permanecem apenas
como informação no relatório.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deskguard.domain.enums import CheckStatus, Severity

PRINTER_STATUS_LABELS: dict[int, str] = {
    1: "Ociosa",
    2: "Imprimindo",
    3: "Offline",
    4: "Papel travado",
    5: "Erro",
    6: "Ocupada",
    7: "Indisponível",
    8: "Aguardando",
    9: "Processando",
    10: "Parada",
    11: "Removida",
    12: "Pausada",
}

DETECTED_ERROR_LABELS: dict[int, str] = {
    1: "Outro erro",
    2: "Sem erro",
    3: "Pouco papel",
    4: "Sem papel",
    5: "Indisponível",
    6: "Serviço solicitado",
    7: "Bandeja de saída cheia",
    8: "Erro geral",
    9: "Papel travado",
    10: "Papel acabou",
    11: "Alimentação manual",
    12: "Entrada/saída de papel",
    13: "Memória baixa",
    14: "Sem papel",
    15: "Offline",
}

EXTENDED_STATUS_LABELS: dict[int, str] = {
    1: "Outro",
    2: "Desconhecido",
    3: "Ociosa",
    4: "Imprimindo",
    5: "Parada",
    6: "Offline",
    7: "Pausada",
    8: "Erro",
    9: "Indisponível",
    10: "Aguardando",
    11: "Processando",
    12: "Parada",
    13: "Removida",
    14: "Bloqueada",
    15: "Sem energia",
    16: "Pouco papel",
    17: "Sem papel",
    18: "Porta aberta",
    19: "Papel travado",
    20: "Offline",
}

JOB_STATUS_LABELS: dict[int, str] = {
    0: "Normal",
    1: "Pausado",
    2: "Erro",
    4: "Excluindo",
    8: "Enfileirando",
    16: "Imprimindo",
    32: "Offline",
    64: "Sem papel",
    128: "Criado",
    256: "Retido",
    512: "Não excluído",
    1024: "Intervenção do usuário",
    2048: "Reiniciando",
    4096: "Concluído",
    16384: "Processando",
}

# O JobStatus e uma mascara de bits: varios estados podem ocorrer ao mesmo
# tempo (por exemplo, 4096 = "Concluido" e 8 = "Enfileirando").
_JOB_FLAGS: tuple[tuple[int, str], ...] = (
    (4096, "Concluído"),
    (16384, "Processando"),
    (2048, "Reiniciando"),
    (1024, "Intervenção do usuário"),
    (512, "Não excluído"),
    (256, "Retido"),
    (128, "Criado"),
    (64, "Sem papel"),
    (32, "Offline"),
    (16, "Imprimindo"),
    (8, "Enfileirando"),
    (4, "Excluindo"),
    (2, "Erro"),
    (1, "Pausado"),
)

# Códigos de PrinterStatus que constituem falha confirmada.
_PRINTER_FAIL = {4, 5, 7}
# Códigos de PrinterStatus que constituem aviso.
_PRINTER_WARN = {10, 12}
# Códigos de DetectedErrorState que não indicam problema.
_DETECTED_OK = {0, 2}
# Bits de JobStatus que constituem falha confirmada.
_JOB_FAIL_FLAGS = (2, 32, 64)
# Bits de JobStatus que constituem aviso.
_JOB_WARN_FLAGS = (1,)

_VIRTUAL_PORT_PREFIXES = ("portprompt:", "shrfax:")
_VIRTUAL_DRIVER_MARKERS = (
    "microsoft software printer driver",
    "microsoft print to pdf",
    "microsoft xps document writer",
    "microsoft shared fax driver",
)


@dataclass(frozen=True, slots=True)
class PrinterState:
    """Estado interpretado de uma impressora."""

    name: str
    state: str
    status: CheckStatus
    severity: Severity
    message: str
    is_virtual: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "status": str(self.status),
            "severity": str(self.severity),
            "message": self.message,
            "is_virtual": self.is_virtual,
        }


def is_virtual_printer(printer: dict[str, Any]) -> bool:
    """Informa se a impressora é uma impressora virtual do próprio Windows.

    Impressoras como "Microsoft Print to PDF", "Microsoft XPS Document Writer",
    "OneNote" e "Fax"     usam portas virtuais (`PORTPROMPT:`) e ficam em estado
    "offline" por construção. Esse estado é esperado e não gera alerta.
    """
    port = str(printer.get("port", "")).strip().lower()
    if any(port.startswith(prefix) for prefix in _VIRTUAL_PORT_PREFIXES):
        return True
    driver = str(printer.get("driver", "")).strip().lower()
    return any(marker in driver for marker in _VIRTUAL_DRIVER_MARKERS)


def classify_printer(printer: dict[str, Any]) -> PrinterState:
    """Interpreta o estado de uma impressora a partir dos campos do WMI."""
    name = str(printer.get("name", "")).strip() or "(sem nome)"
    printer_status = int(printer.get("printer_status", 0) or 0)
    detected_error = int(printer.get("detected_error_state", 0) or 0)
    extended_status = int(printer.get("extended_status", 0) or 0)
    work_offline = bool(printer.get("work_offline", False))
    virtual = is_virtual_printer(printer)

    status_label = PRINTER_STATUS_LABELS.get(printer_status, "desconhecido")
    error_label = DETECTED_ERROR_LABELS.get(detected_error, "não mapeado")
    extended_label = EXTENDED_STATUS_LABELS.get(extended_status, "desconhecido")

    if work_offline:
        return PrinterState(
            name=name,
            state="offline",
            status=CheckStatus.FAIL,
            severity=Severity.HIGH,
            message="A impressora está marcada como offline (WorkOffline).",
            is_virtual=virtual,
        )

    if detected_error not in _DETECTED_OK:
        return PrinterState(
            name=name,
            state="erro",
            status=CheckStatus.FAIL,
            severity=Severity.MEDIUM,
            message=(
                f"A impressora reportou estado de erro "
                f"(código {detected_error} — {error_label})."
            ),
            is_virtual=virtual,
        )

    if printer_status in _PRINTER_FAIL:
        return PrinterState(
            name=name,
            state="erro",
            status=CheckStatus.FAIL,
            severity=Severity.MEDIUM,
            message=f"A impressora reportou estado '{status_label}'.",
            is_virtual=virtual,
        )

    if printer_status in _PRINTER_WARN or extended_status == 7:
        return PrinterState(
            name=name,
            state=extended_label.lower() if extended_status == 7 else status_label.lower(),
            status=CheckStatus.WARN,
            severity=Severity.LOW,
            message=(
                f"A impressora está '{status_label}'"
                + (f" / '{extended_label}'" if extended_status == 7 else "")
                + "."
            ),
            is_virtual=virtual,
        )

    if printer_status == 3:
        if virtual:
            return PrinterState(
                name=name,
                state="offline (impressora virtual)",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message=(
                    "Impressora virtual do Windows; o estado offline é esperado "
                    "enquanto não houver destino de impressão configurado."
                ),
                is_virtual=True,
            )
        return PrinterState(
            name=name,
            state="offline",
            status=CheckStatus.WARN,
            severity=Severity.LOW,
            message=(
                "A impressora reporta estado 'offline', mas nenhum erro "
                "específico foi detectado. Confirme se o dispositivo está "
                "ligado e conectado à rede."
            ),
            is_virtual=False,
        )

    if printer_status == 0 and detected_error == 0:
        return PrinterState(
            name=name,
            state="desconhecido",
            status=CheckStatus.INCONCLUSIVE,
            severity=Severity.INFO,
            message="O Windows não retornou um estado de impressão para este dispositivo.",
            is_virtual=virtual,
        )

    return PrinterState(
        name=name,
        state=status_label.lower(),
        status=CheckStatus.PASS,
        severity=Severity.INFO,
        message=f"Estado da impressora: {status_label}.",
        is_virtual=virtual,
    )


def decode_job_status(value: Any) -> tuple[str, tuple[str, ...]]:
    """Decodifica a máscara de bits ``JobStatus`` em rótulos legíveis.

    Retorna o rótulo combinado e a lista de estados individuais presentes na
    máscara.
    """
    try:
        status = int(value or 0)
    except (TypeError, ValueError):
        return "desconhecido", ()

    if status == 0:
        return "Normal", ()

    labels = tuple(label for bit, label in _JOB_FLAGS if status & bit)
    if not labels:
        return "desconhecido", ()
    return ", ".join(labels), labels


def classify_job(job: dict[str, Any]) -> tuple[CheckStatus, Severity, str]:
    """Interpreta o estado de um trabalho de impressão.

    O ``JobStatus`` é uma máscara de bits: os estados são avaliados por bit,
    e não por igualdade com o valor numérico.
    """
    label, _flags = decode_job_status(job.get("job_status"))
    document = str(job.get("document", "")).strip()
    description = f"Trabalho '{document or 'sem nome'}'"

    try:
        status_value = int(job.get("job_status", 0) or 0)
    except (TypeError, ValueError):
        status_value = 0

    for bit in _JOB_FAIL_FLAGS:
        if status_value & bit:
            rotulo = JOB_STATUS_LABELS.get(bit, str(bit))
            return (
                CheckStatus.FAIL,
                Severity.MEDIUM,
                f"{description} está com erro de impressão ({rotulo}).",
            )

    for bit in _JOB_WARN_FLAGS:
        if status_value & bit:
            return (
                CheckStatus.WARN,
                Severity.LOW,
                f"{description} está pausado na fila.",
            )

    return CheckStatus.PASS, Severity.INFO, f"{description}: {label}."
