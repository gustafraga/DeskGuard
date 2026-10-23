"""Camada desktop do DeskGuard.

A interface web já é completa e roda em ``127.0.0.1``. Esta camada a coloca
dentro de uma **janela nativa do Windows**, sem barra de endereço, sem abas e
sem o ruído de um navegador aberto no meio do atendimento.

O desenho é deliberadamente simples:

1. a API local sobe em uma **thread de background** (uvicorn);
2. a janela nativa aponta para ``http://127.0.0.1:<porta>/``;
3. ao fechar a janela, o servidor é encerrado junto com o processo.

Nenhuma regra de negócio muda de lugar: a janela carrega exatamente a mesma
aplicação FastAPI, com o mesmo token anti-CSRF, os mesmos cabeçalhos de
segurança e o mesmo catálogo. A camada desktop só cuida da janela.

Se o ``pywebview`` não estiver disponível (ou o WebView2 não existir na
máquina), a ferramenta **não falha**: ela avisa no console e oferece abrir a
mesma interface no navegador padrão.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deskguard.config import Settings
from deskguard.errors import DeskGuardError
from deskguard.version import __version__

DEFAULT_WINDOW_TITLE = "DeskGuard"
DEFAULT_WINDOW_WIDTH = 1360
DEFAULT_WINDOW_HEIGHT = 900
SERVER_START_TIMEOUT_S = 20.0
HEALTH_TIMEOUT_S = 2.0


class DesktopError(DeskGuardError):
    """Falha ao preparar a camada desktop."""


class DesktopUnavailableError(DesktopError):
    """A janela nativa não está disponível neste ambiente."""


@dataclass(frozen=True, slots=True)
class DesktopOptions:
    """Parâmetros de abertura da janela desktop."""

    host: str = "127.0.0.1"
    port: int = 8765
    title: str = DEFAULT_WINDOW_TITLE
    width: int = DEFAULT_WINDOW_WIDTH
    height: int = DEFAULT_WINDOW_HEIGHT
    reuse_existing: bool = True
    browser_fallback: bool = True
    open_browser: bool = False
    timeout_s: float = SERVER_START_TIMEOUT_S


# --------------------------------------------------------------------------
# utilidades de rede
# --------------------------------------------------------------------------
def find_free_port(host: str = "127.0.0.1", preferred: int | None = None) -> int:
    """Devolve uma porta livre para escuta local.

    Se ``preferred`` estiver livre, ela é usada: o técnico pode querer a
    porta conhecida. Caso contrário, o sistema escolhe uma porta efêmera.
    """
    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, preferred))
            except OSError:
                pass
            else:
                return preferred

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])


def _fetch_json(url: str, timeout: float = HEALTH_TIMEOUT_S) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            if response.status != 200:
                return None
            payload = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def is_deskguard_server(base_url: str, timeout: float = HEALTH_TIMEOUT_S) -> bool:
    """Diz se já existe uma instância do DeskGuard escutando em ``base_url``.

    A verificação usa a marca ``application`` do endpoint de saúde, para não
    confundir com outro serviço local que responda JSON.
    """
    payload = _fetch_json(f"{base_url}/api/health", timeout=timeout)
    if not payload:
        return False
    return payload.get("application") == "deskguard"


def wait_for_server(base_url: str, timeout_s: float = SERVER_START_TIMEOUT_S) -> bool:
    """Aguarda a API ficar respondendo na URL informada."""
    deadline = time.monotonic() + max(timeout_s, 0.0)
    while time.monotonic() < deadline:
        if is_deskguard_server(base_url, timeout=1.0):
            return True
        time.sleep(0.2)
    return is_deskguard_server(base_url, timeout=1.0)


# --------------------------------------------------------------------------
# servidor em background
# --------------------------------------------------------------------------
class BackgroundServer:
    """Sobe a API local em uma thread e permite encerrá-la depois."""

    def __init__(self, settings: Settings, host: str, port: int) -> None:
        self.settings = settings
        self.host = host
        self.port = port
        self._server: Any = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        import uvicorn

        from deskguard.api.app import create_app

        config = uvicorn.Config(
            create_app(self.settings),
            host=self.host,
            port=self.port,
            log_level=self.settings.log_level.lower(),
            access_log=False,
            use_colors=False,
            log_config=None,
        )
        self._server = uvicorn.Server(config)
        self._server.install_signal_handlers = lambda: None
        self._thread = threading.Thread(
            target=self._server.run, name="deskguard-desktop-server", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=timeout)


# --------------------------------------------------------------------------
# janela nativa
# --------------------------------------------------------------------------
def _load_webview() -> Any:
    try:
        import webview  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        if is_frozen():
            raise DesktopUnavailableError(
                "A janela nativa não está disponível no executável empacotado. "
                "A interface será aberta no navegador padrão."
            ) from exc
        raise DesktopUnavailableError(
            "A camada desktop exige o pacote 'pywebview'. "
            "Instale com: python -m pip install \"deskguard[desktop]\""
        ) from exc
    return webview


def open_native_window(
    url: str,
    title: str = DEFAULT_WINDOW_TITLE,
    width: int = DEFAULT_WINDOW_WIDTH,
    height: int = DEFAULT_WINDOW_HEIGHT,
) -> int:
    """Abre a janela nativa e bloqueia até ela ser fechada.

    Levanta :class:`DesktopUnavailableError` quando o ``pywebview`` não está
    instalado ou quando o WebView2 do Windows não está disponível.
    """
    webview = _load_webview()
    try:
        webview.create_window(
            title,
            url,
            width=width,
            height=height,
            min_size=(900, 640),
            resizable=True,
            frameless=False,
            easy_drag=False,
        )
        webview.start()
    except Exception as exc:  # pragma: no cover - depende do SO
        raise DesktopUnavailableError(
            f"Não foi possível abrir a janela nativa: {exc}. "
            "Verifique se o runtime WebView2 da Microsoft está instalado."
        ) from exc
    return 0


# --------------------------------------------------------------------------
# orquestração
# --------------------------------------------------------------------------
def run_desktop(settings: Settings, options: DesktopOptions) -> int:
    """Executa a aplicação em modo desktop.

    Reaproveita uma instância já em execução (evita o erro de "porta em uso"
    quando o atalho é acionado duas vezes) e, ao final, encerra o servidor
    criado por ela.
    """
    from deskguard.catalog import registry

    registry.load_builtin_procedures()

    preferred_url = f"http://{options.host}:{options.port}"
    reused = options.reuse_existing and is_deskguard_server(preferred_url)

    server: BackgroundServer | None = None
    base_url = preferred_url

    if not reused:
        port = find_free_port(options.host, options.port)
        base_url = f"http://{options.host}:{port}"
        server = BackgroundServer(settings, options.host, port)
        server.start()
        if not wait_for_server(base_url, options.timeout_s):
            server.stop()
            raise DesktopError(
                f"A API local não respondeu em {base_url} dentro de "
                f"{options.timeout_s:.0f} s."
            )

    print("DeskGuard (modo desktop)")
    print(f"  Interface nativa: {base_url}/")
    print(f"  API: {base_url}/api/docs")
    print(f"  Banco de dados: {settings.database_path}")
    if reused:
        print("  Instância já em execução: reutilizada.")
    print("  Feche a janela para encerrar.\n", flush=True)

    try:
        if options.open_browser:
            webbrowser.open(f"{base_url}/")
        open_native_window(
            f"{base_url}/",
            title=options.title,
            width=options.width,
            height=options.height,
        )
    except DesktopUnavailableError as exc:
        print(f"Aviso: {exc}", flush=True)
        if not options.browser_fallback:
            if server is not None:
                server.stop()
            return 2
        print("Abrindo a interface no navegador padrão...")
        webbrowser.open(f"{base_url}/")
        if server is not None:
            try:
                while server.is_running:
                    time.sleep(0.5)
            except KeyboardInterrupt:  # pragma: no cover - interação manual
                pass
    finally:
        if server is not None:
            server.stop()

    return 0


def desktop_health_fingerprint(url: str) -> str:
    """Devolve a marca do DeskGuard exposta pela API local (usada em testes)."""
    payload = _fetch_json(f"{url}/api/health", timeout=HEALTH_TIMEOUT_S) or {}
    return str(payload.get("application", ""))


def is_frozen() -> bool:
    """Diz se o DeskGuard está rodando como executável congelado.

    No build com PyInstaller o pacote ``pywebview`` não é distribuído: a
    interface abre no navegador padrão e as mensagens precisam refletir
    isso, em vez de sugerir a instalação de um pacote.
    """
    return bool(getattr(sys, "frozen", False))


def desktop_availability() -> dict[str, Any]:
    """Informa se a camada desktop pode ser usada nesta máquina.

    Usado pelo ``deskguard doctor`` e pela tela de configurações, para que o
    técnico saiba se o atalho vai abrir uma janela nativa ou cair no
    navegador.
    """
    try:
        import webview  # type: ignore[import-not-found]
    except ImportError:
        if is_frozen():
            return {
                "available": False,
                "reason": (
                    "Executável empacotado: a janela nativa não é distribuída."
                ),
                "hint": (
                    "A interface do DeskGuard será aberta no navegador padrão."
                ),
            }
        return {
            "available": False,
            "reason": "Pacote 'pywebview' não instalado.",
            "hint": 'python -m pip install "deskguard[desktop]"',
        }

    version = _pywebview_version()
    return {
        "available": True,
        "pywebview_version": version,
        "backend": _webview_backend_name(),
        "reason": None,
        "hint": None,
    }


def _pywebview_version() -> str:
    """Versão instalada do pywebview (via metadados do pacote)."""
    try:
        from importlib.metadata import version

        return version("pywebview")
    except Exception:  # pragma: no cover - dependência do ambiente
        return "desconhecida"


def _webview_backend_name() -> str:
    """Nome do backend gráfico que o pywebview usará (informativo)."""
    import sys

    if sys.platform != "win32":
        return "gtk/qt"
    if Path("C:/Program Files (x86)/Microsoft/EdgeWebView/Application").exists():
        return "edgechromium"
    return "edgechromium (WebView2 runtime não encontrado)"


def default_desktop_options(settings: Settings) -> DesktopOptions:
    """Opções derivadas da configuração da plataforma."""
    return DesktopOptions(
        host=settings.host,
        port=settings.port,
        title=f"{DEFAULT_WINDOW_TITLE} {__version__}",
    )


def resolve_desktop_script(project_dir: Path | None = None) -> Path | None:
    """Procura o atalho ``DeskGuard.bat`` dentro do projeto (uso da CLI)."""
    base = project_dir or Path.cwd()
    for candidate in (base / "scripts" / "DeskGuard.bat", base / "DeskGuard.bat"):
        if candidate.is_file():
            return candidate
    return None
