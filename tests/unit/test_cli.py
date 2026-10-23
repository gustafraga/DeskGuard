"""Testes da interface de linha de comando.

O foco é o comando ``targets``, que administra a lista de destinos autorizados
usada pelas sondagens de rede.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from deskguard import cli, desktop
from deskguard.config import Settings


@pytest.fixture()
def ambiente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isola o diretório de dados e o arquivo de destinos autorizados."""
    monkeypatch.setenv("DESKGUARD_HOME", str(tmp_path))
    monkeypatch.setenv(
        "DESKGUARD_ALLOWED_TARGETS_FILE", str(tmp_path / "allowed_targets.json")
    )
    return tmp_path


def test_parser_aceita_o_comando_targets() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["targets", "list"])
    assert args.command == "targets"
    assert args.targets_command == "list"


def test_parser_aceita_o_comando_run_com_parametros() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["run", "network.connectivity", "--param", "targets=a.local"])
    assert args.procedure_id == "network.connectivity"
    assert args.param == ["targets=a.local"]


def test_targets_list_sem_arquivo_mostra_a_situacao(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["targets", "list"]) == 0
    saida = capsys.readouterr().out
    assert "Nenhum destino autorizado" in saida
    assert str(ambiente / "allowed_targets.json") in saida


def test_targets_add_grava_a_autorizacao(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["targets", "add", "intranet.corp.local", "--port", "443"]) == 0
    saida = capsys.readouterr().out
    assert "intranet.corp.local" in saida

    documento = json.loads(
        (ambiente / "allowed_targets.json").read_text(encoding="utf-8")
    )
    assert documento["targets"] == [
        {
            "host": "intranet.corp.local",
            "ports": [443],
            "description": "",
            "ping": True,
        }
    ]


def test_targets_add_aceita_multiplas_portas_e_descricao(
    ambiente: Path,
) -> None:
    assert (
        cli.main(
            [
                "targets",
                "add",
                "10.0.0.5",
                "--port",
                "80",
                "--port",
                "443",
                "--description",
                "Servidor de aplicação",
            ]
        )
        == 0
    )
    documento = json.loads(
        (ambiente / "allowed_targets.json").read_text(encoding="utf-8")
    )
    alvo = documento["targets"][0]
    assert alvo["ports"] == [80, 443]
    assert alvo["description"] == "Servidor de aplicação"


def test_targets_add_pode_desativar_o_icmp(ambiente: Path) -> None:
    assert cli.main(["targets", "add", "10.0.0.5", "--no-ping"]) == 0
    documento = json.loads(
        (ambiente / "allowed_targets.json").read_text(encoding="utf-8")
    )
    assert documento["targets"][0]["ping"] is False


def test_targets_add_substitui_o_destino_existente(ambiente: Path) -> None:
    cli.main(["targets", "add", "10.0.0.5", "--port", "80"])
    cli.main(["targets", "add", "10.0.0.5", "--port", "443"])

    documento = json.loads(
        (ambiente / "allowed_targets.json").read_text(encoding="utf-8")
    )
    assert len(documento["targets"]) == 1
    assert documento["targets"][0]["ports"] == [443]


def test_targets_list_mostra_os_destinos_autorizados(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["targets", "add", "10.0.0.5", "--port", "9100"])
    capsys.readouterr()

    assert cli.main(["targets", "list"]) == 0
    saida = capsys.readouterr().out
    assert "10.0.0.5" in saida
    assert "9100" in saida


def test_targets_remove_revoga_a_autorizacao(ambiente: Path) -> None:
    cli.main(["targets", "add", "10.0.0.5"])
    assert cli.main(["targets", "remove", "10.0.0.5"]) == 0

    documento = json.loads(
        (ambiente / "allowed_targets.json").read_text(encoding="utf-8")
    )
    assert documento["targets"] == []


def test_targets_remove_de_destino_inexistente_falha(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["targets", "remove", "10.0.0.5"]) == 2
    assert "não está na lista" in capsys.readouterr().err


def test_parametro_invalido_na_cli_e_recusado() -> None:
    with pytest.raises(Exception):
        cli._parse_params(["sem_igual"])


def test_sem_argumentos_assume_o_comando_desktop(
    ambiente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplo clique no executável (sem argumentos) abre a janela nativa."""
    chamadas: list[str] = []

    def _falso(settings: Settings, opcoes: desktop.DesktopOptions) -> int:
        chamadas.append("desktop")
        return 0

    monkeypatch.setattr(desktop, "run_desktop", _falso)
    monkeypatch.setattr(sys, "argv", ["DeskGuard.exe"])

    assert cli.main() == 0
    assert chamadas == ["desktop"]


def test_com_argumentos_mantem_a_cli_normal(
    ambiente: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Abrir pelo terminal com argumentos não deve abrir a janela nativa."""

    def _nao_deve_abrir(*args: object, **kwargs: object) -> int:
        raise AssertionError("A janela nativa não deveria abrir com argumentos.")

    monkeypatch.setattr(desktop, "run_desktop", _nao_deve_abrir)

    assert cli.main(["list"]) == 0
    assert "Catálogo DeskGuard" in capsys.readouterr().out
