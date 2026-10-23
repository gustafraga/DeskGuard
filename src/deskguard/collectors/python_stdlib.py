"""Coletas somente leitura implementadas com a biblioteca padrão do Python.

Essas coletas não dependem de PowerShell e cobrem o que já é acessível de
forma confiável pelo processo local: volumes, memória, contexto de execução e
identidade do host.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import string
import sys
from datetime import datetime, timezone
from typing import Any

from deskguard.domain.enums import CheckStatus, Severity
from deskguard.domain.results import CheckResult

DRIVE_FIXED = 3


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def is_admin() -> bool | None:
    """Informa se o processo roda com token administrativo.

    Retorna ``None`` quando não é possível determinar, para não afirmar algo
    que não foi verificado.
    """
    if os.name != "nt":
        try:
            return os.geteuid() == 0
        except AttributeError:  # pragma: no cover - sistemas POSIX sem geteuid
            return None
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 - esta função só informa, nunca falha
        return None


def logical_drives() -> list[str]:
    """Lista as letras de unidade visíveis para o processo."""
    if os.name != "nt":
        return ["/"]

    try:
        mask = int(ctypes.windll.kernel32.GetLogicalDrives())
    except Exception:  # noqa: BLE001
        return []

    drives: list[str] = []
    for index, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << index):
            drives.append(f"{letter}:\\")
    return drives


def drive_type(path: str) -> int | None:
    """Tipo da unidade (3 = fixa). Retorna ``None`` se não for possível."""
    if os.name != "nt":
        return DRIVE_FIXED
    try:
        return int(ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(path)))
    except Exception:  # noqa: BLE001
        return None


def memory_status() -> dict[str, Any] | None:
    """Uso atual de memória física. ``None`` quando indisponível."""
    if os.name != "nt":
        try:
            usage = shutil.disk_usage  # placeholder nunca usado em POSIX
        except Exception:  # noqa: BLE001
            return None
        return None
    try:
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    except Exception:  # noqa: BLE001
        return None
    return {
        "total_bytes": int(status.ullTotalPhys),
        "available_bytes": int(status.ullAvailPhys),
        "load_percent": int(status.dwMemoryLoad),
        "total_gb": round(status.ullTotalPhys / 1024**3, 2),
        "available_gb": round(status.ullAvailPhys / 1024**3, 2),
    }


def collect_runtime(ctx: Any) -> CheckResult:
    """Contexto de execução: interpretador, processador e privilégios."""
    try:
        admin = is_admin()
        memory = memory_status()
        evidence: dict[str, Any] = {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "process_id": os.getpid(),
            "cpu_count": os.cpu_count(),
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.architecture()[0],
            "bitness": 64 if sys.maxsize > 2**32 else 32,
            "is_admin": admin,
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if memory:
            evidence["memory"] = memory

        if admin is False:
            # Executar sem elevação é a condição normal de um posto de trabalho.
            # Não é um desvio do endpoint: é uma limitação do coletor, e por isso
            # não pode ser reportado como "falha confirmada".
            message = (
                "Processo executado com privilégios de usuário padrão. Coletas que "
                "exigem elevação serão marcadas como inconclusivas, não como falha."
            )
            return CheckResult.ok(
                "system.runtime",
                "Contexto de execução",
                message,
                evidence=evidence,
            )

        return CheckResult.ok(
            "system.runtime",
            "Contexto de execução",
            "Contexto de execução obtido com sucesso.",
            evidence=evidence,
        )
    except Exception as exc:  # noqa: BLE001 - fronteira de isolamento
        return CheckResult.inconclusive(
            "system.runtime",
            "Contexto de execução",
            "Não foi possível coletar o contexto de execução.",
            error_code="PYTHON_COLLECTOR_ERROR",
            evidence={"exception_message": str(exc)[:300]},
        )


def collect_storage(ctx: Any) -> CheckResult:
    """Espaço em disco das unidades fixas do endpoint."""
    volumes: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in logical_drives():
        kind = drive_type(path)
        if kind is not None and kind != DRIVE_FIXED:
            continue
        try:
            usage = shutil.disk_usage(path)
        except (OSError, PermissionError) as exc:
            errors.append(f"{path}: {exc.strerror or exc}")
            continue
        total = usage.total
        free = usage.free
        used = total - free
        volumes.append(
            {
                "path": path,
                "total_bytes": total,
                "free_bytes": free,
                "used_bytes": used,
                "total_gb": round(total / 1024**3, 2),
                "free_gb": round(free / 1024**3, 2),
                "used_percent": round((used / total) * 100, 1) if total else None,
            }
        )

    if not volumes:
        return CheckResult.inconclusive(
            "system.storage",
            "Armazenamento",
            "Nenhuma unidade fixa pôde ser consultada.",
            error_code="STORAGE_UNAVAILABLE",
            evidence={"errors": errors},
        )

    critical = [v for v in volumes if (v["used_percent"] or 0) >= 90]
    warnings = [v for v in volumes if 80 <= (v["used_percent"] or 0) < 90]

    evidence = {"volumes": volumes, "errors": errors}
    if critical:
        return CheckResult.fail(
            "system.storage",
            "Armazenamento",
            f"{len(critical)} unidade(s) com uso igual ou superior a 90%.",
            severity=Severity.HIGH,
            evidence=evidence,
            remediation="Avaliar limpeza ou expansão de volume antes de abrir chamado de lentidão.",
        )
    if warnings:
        return CheckResult.warning(
            "system.storage",
            "Armazenamento",
            f"{len(warnings)} unidade(s) com uso entre 80% e 90%.",
            severity=Severity.LOW,
            evidence=evidence,
            remediation="Monitorar crescimento de volume.",
        )
    return CheckResult.ok(
        "system.storage",
        "Armazenamento",
        f"{len(volumes)} unidade(s) fixa(s) verificada(s).",
        evidence=evidence,
    )


def dns_lookup(hostname: str, timeout_s: float = 5.0) -> tuple[bool, list[str], str | None]:
    """Resolve um nome. Retorna (sucesso, endereços, mensagem de erro)."""
    import socket

    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_s)
    try:
        infos = socket.getaddrinfo(hostname, None)
        addresses = sorted({info[4][0] for info in infos})
        return True, addresses, None
    except socket.gaierror as exc:
        return False, [], f"Erro de resolução DNS: {exc.strerror or exc}"
    except socket.timeout:
        return False, [], "Tempo esgotado durante a resolução DNS."
    except OSError as exc:
        return False, [], f"Falha de rede durante a resolução DNS: {exc}"
    finally:
        socket.setdefaulttimeout(previous)


def tcp_probe(host: str, port: int, timeout_s: float = 5.0) -> tuple[bool, str | None]:
    """Testa uma conexão TCP. Retorna (sucesso, mensagem de erro)."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True, None
    except socket.timeout:
        return False, f"Tempo esgotado ao conectar em {host}:{port}."
    except ConnectionRefusedError:
        return False, f"Conexão recusada em {host}:{port}."
    except OSError as exc:
        return False, f"Falha ao conectar em {host}:{port}: {exc}."


def status_is_inconclusive(status: CheckStatus) -> bool:
    return status is CheckStatus.INCONCLUSIVE
