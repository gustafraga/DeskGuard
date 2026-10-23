"""Testes da camada desktop (janela nativa do Windows).

A camada desktop tem duas partes:

1. a rede local (``find_free_port``, ``is_deskguard_server``,
   ``wait_for_server``, ``BackgroundServer``) — testada de verdade, inclusive
   com um servidor uvicorn real em thread;
2. a janela nativa (``pywebview``) — que não pode ser aberta durante a
   suíte, então é substituída por um dublê.

Nenhum teste aqui abre uma janela gráfica, consulta o sistema operacional nem
altera o computador do operador.
"""

from __future__ import annotations

import json
import socket
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from deskguard import cli, desktop
from deskguard.config import Settings
from deskguard.desktop import (
    BackgroundServer,
    DesktopError,
    DesktopOptions,
    DesktopUnavailableError,
    default_desktop_options,
    desktop_availability,
    desktop_health_fingerprint,
    find_free_port,
    is_deskguard_server,
    open_native_window,
    resolve_desktop_script,
    run_desktop,
    wait_for_server,
)
from deskguard.version import __version__


# --------------------------------------------------------------------------
# dublês
# --------------------------------------------------------------------------
class _WebviewFalso:
    """Substitui o módulo ``webview`` durante os testes."""

    def __init__(self) -> None:
        self.janelas: list[dict[str, Any]] = []
        self.iniciado = False

    def create_window(self, title: str, url: str, **kwargs: Any) -> None:
        self.janelas.append({"title": title, "url": url, **kwargs})

    def start(self) -> None:
        self.iniciado = True


class _ServidorFalso:
    """Servidor de background que não sobe nada de verdade."""

    instanciado = 0

    def __init__(self, settings: Settings, host: str, port: int) -> None:
        type(self).instanciado += 1
        self.settings = settings
        self.host = host
        self.port = port
        self.iniciado = False
        self.parado = False

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        return self.iniciado and not self.parado

    def start(self) -> None:
        self.iniciado = True

    def stop(self, timeout: float = 5.0) -> None:
        self.parado = True


class _ServidorEfemero(_ServidorFalso):
    """Servidor que se apaga sozinho.

    No mundo real o servidor vive até o técnico fechar a janela; o dublê
    imita esse comportamento parando depois de algumas consultas, para que o
    teste não fique esperando.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.consultas = 0

    @property
    def is_running(self) -> bool:
        self.consultas += 1
        return self.consultas < 3


def _porta_livre() -> int:
    """Reserva uma porta efêmera e devolve o número."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture()
def webview_falso(monkeypatch: pytest.MonkeyPatch) -> _WebviewFalso:
    """Instala um módulo ``webview`` de mentira no ``sys.modules``."""
    modulo = _WebviewFalso()
    monkeypatch.setitem(sys.modules, "webview", modulo)
    return modulo


@pytest.fixture()
def sem_webview(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simula uma máquina em que o ``pywebview`` não está instalado."""
    monkeypatch.setitem(sys.modules, "webview", None)


@pytest.fixture()
def autoplay(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Impede que os testes abram o navegador padrão."""
    abertas: list[str] = []

    def _open(url: str) -> bool:
        abertas.append(url)
        return True

    monkeypatch.setattr(desktop.webbrowser, "open", _open)
    return abertas


# --------------------------------------------------------------------------
# rede local
# --------------------------------------------------------------------------
def test_find_free_port_usa_a_porta_preferida_quando_esta_livre() -> None:
    porta = _porta_livre()
    assert find_free_port("127.0.0.1", porta) == porta


def test_find_free_port_ignora_a_porta_ocupada() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ocupado:
        ocupado.bind(("127.0.0.1", 0))
        ocupado.listen(1)
        porta = int(ocupado.getsockname()[1])

        escolhida = find_free_port("127.0.0.1", porta)

    assert escolhida != porta
    assert 0 < escolhida < 65536


def test_find_free_port_sem_preferencia_escolhe_uma_porta_efemera() -> None:
    porta = find_free_port("127.0.0.1", None)
    assert 0 < porta < 65536


def test_fetch_json_devolve_none_quando_a_resposta_nao_e_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Resposta:
        status = 200

        def read(self) -> bytes:
            return b"nao e json"

        def __enter__(self) -> "_Resposta":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resposta())
    assert desktop._fetch_json("http://127.0.0.1:8765/api/health") is None


def test_fetch_json_devolve_none_quando_a_conexao_falha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _falha(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("sem conexão")

    monkeypatch.setattr(urllib.request, "urlopen", _falha)
    assert desktop._fetch_json("http://127.0.0.1:8765/api/health") is None


def test_fetch_json_devolve_o_objeto_decodificado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Resposta:
        status = 200

        def read(self) -> bytes:
            return json.dumps({"application": "deskguard", "status": "ok"}).encode()

        def __enter__(self) -> "_Resposta":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resposta())
    payload = desktop._fetch_json("http://127.0.0.1:8765/api/health")
    assert payload == {"application": "deskguard", "status": "ok"}


def test_is_deskguard_server_usa_a_marca_da_aplicacao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop, "_fetch_json", lambda *a, **k: {"application": "deskguard"}
    )
    assert is_deskguard_server("http://127.0.0.1:8765") is True


def test_is_deskguard_server_ignora_outro_servico_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop, "_fetch_json", lambda *a, **k: {"application": "outro-servico"}
    )
    assert is_deskguard_server("http://127.0.0.1:8765") is False


def test_is_deskguard_server_e_falso_sem_resposta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop, "_fetch_json", lambda *a, **k: None)
    assert is_deskguard_server("http://127.0.0.1:8765") is False


def test_wait_for_server_aguarda_a_api_subir(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[str] = []

    def _fake(base_url: str, timeout: float = 1.0) -> bool:
        chamadas.append(base_url)
        return len(chamadas) >= 3

    monkeypatch.setattr(desktop, "is_deskguard_server", _fake)
    assert wait_for_server("http://127.0.0.1:8765", timeout_s=5.0) is True
    assert len(chamadas) >= 3


def test_wait_for_server_devolve_false_quando_a_api_nao_sobe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop, "is_deskguard_server", lambda *a, **k: False)
    assert wait_for_server("http://127.0.0.1:8765", timeout_s=0.1) is False


def test_background_server_sobe_e_responde(settings: Settings) -> None:
    """Sobe a API real em thread e confirma a marca do DeskGuard."""
    porta = _porta_livre()
    servidor = BackgroundServer(settings, "127.0.0.1", porta)
    servidor.start()
    try:
        assert servidor.is_running is True
        assert servidor.base_url == f"http://127.0.0.1:{porta}"
        assert wait_for_server(servidor.base_url, timeout_s=20.0) is True
        assert desktop_health_fingerprint(servidor.base_url) == "deskguard"
    finally:
        servidor.stop()

    assert servidor.is_running is False


def test_background_server_stop_e_idempotente(settings: Settings) -> None:
    servidor = BackgroundServer(settings, "127.0.0.1", _porta_livre())
    servidor.start()
    servidor.stop()
    servidor.stop()
    assert servidor.is_running is False


# --------------------------------------------------------------------------
# janela nativa
# --------------------------------------------------------------------------
def test_open_native_window_cria_a_janela_com_a_url(
    webview_falso: _WebviewFalso,
) -> None:
    assert open_native_window("http://127.0.0.1:8765/", title="DeskGuard") == 0
    assert webview_falso.iniciado is True
    assert len(webview_falso.janelas) == 1
    janela = webview_falso.janelas[0]
    assert janela["url"] == "http://127.0.0.1:8765/"
    assert janela["title"] == "DeskGuard"
    assert janela["resizable"] is True
    assert janela["min_size"] == (900, 640)


def test_open_native_window_sem_pywebview_falha_com_mensagem_clara(
    sem_webview: None,
) -> None:
    with pytest.raises(DesktopUnavailableError) as erro:
        open_native_window("http://127.0.0.1:8765/")
    assert "pywebview" in str(erro.value)


def test_load_webview_relata_a_instalacao_ausente(sem_webview: None) -> None:
    with pytest.raises(DesktopUnavailableError):
        desktop._load_webview()


def test_load_webview_devolve_o_modulo_instalado(webview_falso: _WebviewFalso) -> None:
    assert desktop._load_webview() is webview_falso


# --------------------------------------------------------------------------
# orquestração
# --------------------------------------------------------------------------
def test_run_desktop_reaproveita_a_instancia_existente(
    monkeypatch: pytest.MonkeyPatch,
    webview_falso: _WebviewFalso,
    autoplay: list[str],
    settings: Settings,
) -> None:
    monkeypatch.setattr(desktop, "is_deskguard_server", lambda *a, **k: True)

    def _nao_deve_criar(*args: object, **kwargs: object) -> None:
        raise AssertionError("Um servidor novo não deveria ser criado.")

    monkeypatch.setattr(desktop, "BackgroundServer", _nao_deve_criar)

    opcoes = DesktopOptions(host="127.0.0.1", port=8765)
    assert run_desktop(settings, opcoes) == 0
    assert webview_falso.janelas[0]["url"] == "http://127.0.0.1:8765/"
    assert autoplay == []


def test_run_desktop_sobe_o_servidor_quando_nao_ha_instancia(
    monkeypatch: pytest.MonkeyPatch,
    webview_falso: _WebviewFalso,
    settings: Settings,
) -> None:
    _ServidorFalso.instanciado = 0
    monkeypatch.setattr(desktop, "is_deskguard_server", lambda *a, **k: False)
    monkeypatch.setattr(desktop, "find_free_port", lambda host, preferred=None: 8999)
    monkeypatch.setattr(desktop, "wait_for_server", lambda *a, **k: True)
    monkeypatch.setattr(desktop, "BackgroundServer", _ServidorFalso)

    opcoes = DesktopOptions(host="127.0.0.1", port=8765)
    assert run_desktop(settings, opcoes) == 0
    assert _ServidorFalso.instanciado == 1
    assert webview_falso.janelas[0]["url"] == "http://127.0.0.1:8999/"


def test_run_desktop_falha_quando_a_api_nao_responde(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    _ServidorFalso.instanciado = 0
    monkeypatch.setattr(desktop, "is_deskguard_server", lambda *a, **k: False)
    monkeypatch.setattr(desktop, "find_free_port", lambda host, preferred=None: 8999)
    monkeypatch.setattr(desktop, "wait_for_server", lambda *a, **k: False)
    monkeypatch.setattr(desktop, "BackgroundServer", _ServidorFalso)

    opcoes = DesktopOptions(host="127.0.0.1", port=8765, timeout_s=1.0)
    with pytest.raises(DesktopError):
        run_desktop(settings, opcoes)
    assert _ServidorFalso.instanciado == 1


def test_run_desktop_sem_fallback_para_o_navegador(
    monkeypatch: pytest.MonkeyPatch,
    autoplay: list[str],
    settings: Settings,
) -> None:
    monkeypatch.setattr(desktop, "is_deskguard_server", lambda *a, **k: False)
    monkeypatch.setattr(desktop, "find_free_port", lambda host, preferred=None: 8999)
    monkeypatch.setattr(desktop, "wait_for_server", lambda *a, **k: True)
    monkeypatch.setattr(desktop, "BackgroundServer", _ServidorFalso)

    def _sem_janela(*args: object, **kwargs: object) -> int:
        raise DesktopUnavailableError("WebView2 ausente.")

    monkeypatch.setattr(desktop, "open_native_window", _sem_janela)

    opcoes = DesktopOptions(host="127.0.0.1", port=8765, browser_fallback=False)
    assert run_desktop(settings, opcoes) == 2
    assert autoplay == []


def test_run_desktop_usa_o_navegador_quando_a_janela_falha(
    monkeypatch: pytest.MonkeyPatch,
    autoplay: list[str],
    settings: Settings,
) -> None:
    monkeypatch.setattr(desktop, "is_deskguard_server", lambda *a, **k: False)
    monkeypatch.setattr(desktop, "find_free_port", lambda host, preferred=None: 8999)
    monkeypatch.setattr(desktop, "wait_for_server", lambda *a, **k: True)
    monkeypatch.setattr(desktop, "BackgroundServer", _ServidorEfemero)
    monkeypatch.setattr(desktop.time, "sleep", lambda *_: None)

    def _sem_janela(*args: object, **kwargs: object) -> int:
        raise DesktopUnavailableError("WebView2 ausente.")

    monkeypatch.setattr(desktop, "open_native_window", _sem_janela)

    opcoes = DesktopOptions(host="127.0.0.1", port=8765, browser_fallback=True)
    assert run_desktop(settings, opcoes) == 0
    assert autoplay == ["http://127.0.0.1:8999/"]


def test_run_desktop_pode_abrir_o_navegador_alem_da_janela(
    monkeypatch: pytest.MonkeyPatch,
    webview_falso: _WebviewFalso,
    autoplay: list[str],
    settings: Settings,
) -> None:
    monkeypatch.setattr(desktop, "is_deskguard_server", lambda *a, **k: True)
    opcoes = DesktopOptions(host="127.0.0.1", port=8765, open_browser=True)
    assert run_desktop(settings, opcoes) == 0
    assert autoplay == ["http://127.0.0.1:8765/"]


def test_run_desktop_encerra_o_servidor_ao_fechar_a_janela(
    monkeypatch: pytest.MonkeyPatch,
    webview_falso: _WebviewFalso,
    settings: Settings,
) -> None:
    instancias: list[_ServidorFalso] = []

    class _Servidor(_ServidorFalso):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]
            instancias.append(self)

    monkeypatch.setattr(desktop, "is_deskguard_server", lambda *a, **k: False)
    monkeypatch.setattr(desktop, "find_free_port", lambda host, preferred=None: 8999)
    monkeypatch.setattr(desktop, "wait_for_server", lambda *a, **k: True)
    monkeypatch.setattr(desktop, "BackgroundServer", _Servidor)

    assert run_desktop(settings, DesktopOptions(host="127.0.0.1", port=8765)) == 0
    assert instancias[0].parado is True


# --------------------------------------------------------------------------
# diagnóstico da camada desktop
# --------------------------------------------------------------------------
def test_desktop_availability_sem_pywebview(sem_webview: None) -> None:
    informacao = desktop_availability()
    assert informacao["available"] is False
    assert "pywebview" in informacao["reason"]
    assert "pip install" in informacao["hint"]


def test_executavel_congelado_e_reconhecido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    assert desktop.is_frozen() is True
    monkeypatch.delattr(desktop.sys, "frozen", raising=False)
    assert desktop.is_frozen() is False


def test_desktop_availability_no_executavel_congelado(
    monkeypatch: pytest.MonkeyPatch,
    sem_webview: None,
) -> None:
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    informacao = desktop_availability()
    assert informacao["available"] is False
    assert "empacotado" in informacao["reason"]
    assert "navegador padrão" in informacao["hint"]


def test_load_webview_no_executavel_congelado(
    monkeypatch: pytest.MonkeyPatch,
    sem_webview: None,
) -> None:
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    with pytest.raises(DesktopUnavailableError) as erro:
        desktop._load_webview()
    assert "empacotado" in str(erro.value)


def test_desktop_availability_com_pywebview(
    webview_falso: _WebviewFalso,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop, "_pywebview_version", lambda: "6.2.1")
    informacao = desktop_availability()
    assert informacao["available"] is True
    assert informacao["pywebview_version"] == "6.2.1"
    assert informacao["reason"] is None
    assert informacao["backend"]


def test_backend_do_webview_e_identificado() -> None:
    backend = desktop._webview_backend_name()
    assert isinstance(backend, str)
    assert backend


def test_default_desktop_options_usa_a_configuracao(settings: Settings) -> None:
    opcoes = default_desktop_options(settings)
    assert opcoes.host == settings.host
    assert opcoes.port == settings.port
    assert "DeskGuard" in opcoes.title
    assert __version__ in opcoes.title


def test_resolve_desktop_script_encontra_o_atalho(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    atalho = scripts / "DeskGuard.bat"
    atalho.write_text("@echo off\n", encoding="ascii")

    encontrado = resolve_desktop_script(tmp_path)
    assert encontrado == atalho


def test_resolve_desktop_script_aceita_a_raiz_do_projeto(tmp_path: Path) -> None:
    atalho = tmp_path / "DeskGuard.bat"
    atalho.write_text("@echo off\n", encoding="ascii")

    assert resolve_desktop_script(tmp_path) == atalho


def test_resolve_desktop_script_devolve_none_quando_nao_existe(
    tmp_path: Path,
) -> None:
    assert resolve_desktop_script(tmp_path) is None


def test_desktop_health_fingerprint_usa_a_api_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop, "_fetch_json", lambda *a, **k: {"application": "deskguard"}
    )
    assert desktop_health_fingerprint("http://127.0.0.1:8765") == "deskguard"


def test_desktop_health_fingerprint_sem_resposta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop, "_fetch_json", lambda *a, **k: None)
    assert desktop_health_fingerprint("http://127.0.0.1:8765") == ""


# --------------------------------------------------------------------------
# comando de linha de comando
# --------------------------------------------------------------------------
def test_parser_aceita_o_comando_desktop() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["desktop", "--port", "9100", "--title", "Teste"])
    assert args.command == "desktop"
    assert args.port == 9100
    assert args.title == "Teste"
    assert args.no_reuse is False
    assert args.no_browser_fallback is False
    assert args.open_browser is False


def test_comando_desktop_transmite_as_opcoes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DESKGUARD_HOME", str(tmp_path))
    recebidas: list[DesktopOptions] = []

    def _falso(settings: Settings, opcoes: DesktopOptions) -> int:
        recebidas.append(opcoes)
        return 0

    monkeypatch.setattr(desktop, "run_desktop", _falso)

    codigo = cli.main(
        ["desktop", "--port", "9100", "--title", "Teste", "--no-reuse"]
    )

    assert codigo == 0
    assert len(recebidas) == 1
    opcoes = recebidas[0]
    assert opcoes.port == 9100
    assert opcoes.title == "Teste"
    assert opcoes.reuse_existing is False
    assert opcoes.browser_fallback is True


def test_comando_desktop_relata_a_falha_de_inicializacao(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DESKGUARD_HOME", str(tmp_path))

    def _falso(settings: Settings, opcoes: DesktopOptions) -> int:
        raise DesktopError("A API local não respondeu.")

    monkeypatch.setattr(desktop, "run_desktop", _falso)

    assert cli.main(["desktop"]) == 2
    assert "A API local não respondeu" in capsys.readouterr().err
