"""Executor seguro de scripts PowerShell.

Princípios de segurança aplicados aqui:

* Nenhum valor recebido do usuário chega à linha de comando. Os parâmetros
  trafegam por arquivo JSON temporário, cujo caminho é informado ao processo
  por variável de ambiente.
* Os scripts são arquivos versionados no projeto, carregados por caminho
  absoluto resolvido a partir do pacote instalado. Não há concatenação de
  comandos.
* `-NoProfile` e `-NonInteractive` evitam que scripts de perfil do usuário ou
  prompts interativos alterem o comportamento ou bloqueiem a execução.
* Todo comando tem limite de tempo e qualquer falha vira resultado
  inconclusivo, nunca uma falha confirmada.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deskguard.collectors.base import ProbeContext
from deskguard.domain.results import CheckResult
from deskguard.errors import CollectorError

_SCRIPT_PACKAGE = "deskguard.collectors.scripts"

# O Windows impõe um limite de 32.767 caracteres para a linha de comando criada
# por CreateProcess. O script é entregue por -EncodedCommand, que dobra o
# tamanho em UTF-16LE antes da codificação base64; por isso os scripts .ps1
# precisam ser mantidos pequenos. O limite abaixo fica abaixo do limite real
# para que o excesso seja reportado como erro legível, e não como WinError 206.
_MAX_ENCODED_COMMAND_CHARS = 32_000
_MAX_ENCODED_COMMAND_MESSAGE = (
    "O script '{name}' excede o limite de {limit} caracteres codificados "
    "permitido na linha de comando do Windows. Reduza o tamanho do script "
    "(comentarios e blocos de codigo) ou divida a coleta em etapas menores."
)


def _powershell_path() -> Path:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def script_path(script_name: str) -> Path:
    """Resolve o caminho absoluto de um script versionado no pacote."""
    from importlib.resources import files

    resource = files(_SCRIPT_PACKAGE).joinpath(script_name)
    return Path(str(resource))


@dataclass(frozen=True, slots=True)
class PowerShellOutcome:
    """Resultado bruto da execução de um script."""

    ok: bool
    payload: dict[str, Any]
    stdout: str
    stderr: str
    duration_ms: int
    returncode: int | None


class PowerShellRunner:
    """Executa scripts PowerShell versionados com parâmetros isolados."""

    def __init__(self, executable: Path | None = None) -> None:
        self.executable = executable or _powershell_path()

    @property
    def available(self) -> bool:
        return self.executable.exists()

    def run_script(
        self,
        script: Path,
        payload: dict[str, Any] | None = None,
        *,
        timeout_s: float = 20.0,
    ) -> PowerShellOutcome:
        if not self.available:
            raise CollectorError(
                f"PowerShell não encontrado em {self.executable}."
            )
        if not script.exists():
            raise CollectorError(f"Script não encontrado: {script}")

        payload = payload or {}
        encoded = _encode_command(script)
        if len(encoded) > _MAX_ENCODED_COMMAND_CHARS:
            raise CollectorError(
                _MAX_ENCODED_COMMAND_MESSAGE.format(
                    name=script.name, limit=_MAX_ENCODED_COMMAND_CHARS
                )
            )
        started = time.perf_counter()
        handle, payload_file = tempfile.mkstemp(suffix=".json", prefix="deskguard_")
        os.close(handle)
        try:
            Path(payload_file).write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            env = dict(os.environ)
            env["DESKGUARD_PAYLOAD_PATH"] = payload_file
            # Evita que o PowerShell trave aguardando entrada do console.
            env["POWERSHELL_TELEMETRY_OPTOUT"] = "1"

            creation_flags = 0
            if os.name == "nt":
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            completed = subprocess.run(
                [
                    str(self.executable),
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded,
                ],
                capture_output=True,
                timeout=timeout_s,
                env=env,
                cwd=str(script.parent),
                creationflags=creation_flags,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CollectorError(
                f"O script '{script.name}' excedeu o limite de {timeout_s:.0f}s."
            ) from exc
        finally:
            _cleanup(payload_file)

        duration_ms = int((time.perf_counter() - started) * 1000)
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        parsed = _parse_output(stdout)

        if completed.returncode != 0 and not parsed:
            raise CollectorError(
                f"O script '{script.name}' terminou com código {completed.returncode}: "
                f"{stderr.strip()[:300]}"
            )
        return PowerShellOutcome(
            ok=bool(parsed.get("ok", completed.returncode == 0)),
            payload=parsed.get("data") or {},
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            returncode=completed.returncode,
        )

    def run_collector(
        self,
        script_name: str,
        payload: dict[str, Any] | None,
        ctx: ProbeContext,
        *,
        check_id: str,
        title: str,
        error_code: str = "POWERSHELL_ERROR",
    ) -> CheckResult:
        """Executa um script e converte qualquer falha em resultado inconclusivo."""
        try:
            outcome = self.run_script(
                script_path(script_name), payload, timeout_s=ctx.timeout_s
            )
        except CollectorError as exc:
            return CheckResult.inconclusive(
                check_id,
                title,
                "Não foi possível executar a coleta via PowerShell neste endpoint.",
                error_code=error_code,
                evidence={"detail": str(exc)[:400]},
            )
        except Exception as exc:  # noqa: BLE001 - fronteira de isolamento
            return CheckResult.inconclusive(
                check_id,
                title,
                "Falha inesperada durante a coleta via PowerShell.",
                error_code=error_code,
                evidence={
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc)[:400],
                },
            )

        if not outcome.ok:
            return CheckResult.inconclusive(
                check_id,
                title,
                "O script de coleta retornou uma execução incompleta.",
                error_code=error_code,
                evidence={
                    "stderr": outcome.stderr.strip()[:400],
                    "returncode": outcome.returncode,
                },
                duration_ms=outcome.duration_ms,
            )

        return CheckResult.ok(
            check_id,
            title,
            "Coleta concluída.",
            evidence=outcome.payload,
            duration_ms=outcome.duration_ms,
        )


def _encode_command(script: Path) -> str:
    """Codifica o script em base64 UTF-16LE para uso com -EncodedCommand.

    O conteúdo é sempre um arquivo versionado do projeto: nenhum texto
    originado de usuário entra nesta etapa. A leitura tolera BOM, para que a
    codificação do arquivo nunca altere o script entregue ao PowerShell.
    """
    import base64

    text = script.read_text(encoding="utf-8-sig")
    return base64.b64encode(text.encode("utf-16-le")).decode("ascii")


def _parse_output(stdout: str) -> dict[str, Any]:
    """Extrai o objeto JSON final emitido pelo script."""
    text = stdout.strip()
    if not text:
        return {}
    start = text.find("{")
    if start == -1:
        return {}
    candidate = text[start:]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
