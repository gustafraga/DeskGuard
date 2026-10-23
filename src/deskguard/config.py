"""Configuração da plataforma, resolvida a partir do ambiente.

Todo o estado persistente fica em um diretório local do usuário. Nenhuma
configuração apontará para um servidor remoto: a premissa do DeskGuard é a
execução local, no próprio endpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from deskguard.domain.enums import ExecutionMode

APP_NAME = "DeskGuard"
APP_SLUG = "deskguard"


def _default_data_dir() -> Path:
    override = os.environ.get("DESKGUARD_HOME")
    if override:
        return Path(override).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME
    return Path.home() / ".local" / "share" / APP_SLUG


@dataclass(frozen=True, slots=True)
class Settings:
    """Parâmetros de execução do DeskGuard."""

    data_dir: Path
    database_path: Path
    host: str = "127.0.0.1"
    port: int = 8765
    request_timeout_s: float = 25.0
    max_concurrent_executions: int = 2
    mode: ExecutionMode = ExecutionMode.LIVE
    log_level: str = "INFO"
    open_browser: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        environ = os.environ if env is None else env
        data_dir = Path(environ.get("DESKGUARD_HOME") or _default_data_dir()).expanduser()
        db_path_raw = environ.get("DESKGUARD_DB") or str(data_dir / "deskguard.db")
        database_path = Path(db_path_raw).expanduser()

        mode_raw = (environ.get("DESKGUARD_MODE") or ExecutionMode.LIVE.value).lower()
        mode = ExecutionMode.DEMO if mode_raw == ExecutionMode.DEMO.value else ExecutionMode.LIVE

        def _int(name: str, default: int) -> int:
            raw = environ.get(name)
            if not raw:
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        def _float(name: str, default: float) -> float:
            raw = environ.get(name)
            if not raw:
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        return cls(
            data_dir=data_dir,
            database_path=database_path,
            host=environ.get("DESKGUARD_HOST", "127.0.0.1"),
            port=_int("DESKGUARD_PORT", 8765),
            request_timeout_s=_float("DESKGUARD_TIMEOUT", 25.0),
            max_concurrent_executions=_int("DESKGUARD_MAX_CONCURRENCY", 2),
            mode=mode,
            log_level=environ.get("DESKGUARD_LOG_LEVEL", "INFO").upper(),
            open_browser=environ.get("DESKGUARD_OPEN_BROWSER", "").lower() in {"1", "true", "yes"},
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "data_dir": str(self.data_dir),
            "database_path": str(self.database_path),
            "host": self.host,
            "port": self.port,
            "request_timeout_s": self.request_timeout_s,
            "max_concurrent_executions": self.max_concurrent_executions,
            "mode": str(self.mode),
        }
