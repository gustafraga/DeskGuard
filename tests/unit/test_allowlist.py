"""Testes da lista de destinos autorizados.

A lista é a barreira que impede o DeskGuard de ser usado como sonda para
redes arbitrárias. Estes testes cobrem a leitura, a gravação e, sobretudo,
as regras de recusa.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deskguard.security.allowlist import (
    ALLOWLIST_FILENAME,
    DEFAULT_PORTS,
    MAX_PORTS_PER_TARGET,
    MAX_TARGETS,
    AllowedTarget,
    AllowlistError,
    TargetAllowlist,
    default_allowlist_path,
    is_ip_literal,
    is_valid_host,
    load_allowlist,
    save_allowlist,
)


def test_arquivo_inexistente_resulta_em_lista_vazia(tmp_path: Path) -> None:
    allowlist = load_allowlist(tmp_path / "nao_existe.json")
    assert allowlist.targets == ()
    assert allowlist.available is False
    assert allowlist.is_empty() is True


def test_arquivo_invalido_resulta_em_lista_vazia_com_aviso(tmp_path: Path) -> None:
    caminho = tmp_path / ALLOWLIST_FILENAME
    caminho.write_text("{isto nao e json", encoding="utf-8")

    allowlist = load_allowlist(caminho)
    assert allowlist.targets == ()
    assert allowlist.available is False
    assert allowlist.warnings


def test_leitura_de_lista_com_dois_formatos(tmp_path: Path) -> None:
    caminho = tmp_path / ALLOWLIST_FILENAME
    caminho.write_text(
        json.dumps(
            {
                "targets": [
                    {"host": "intranet.corp.local", "ports": [443]},
                    {"host": "10.0.0.5", "ports": [3389], "ping": False},
                ]
            }
        ),
        encoding="utf-8",
    )

    allowlist = load_allowlist(caminho)
    assert allowlist.available is True
    assert allowlist.hosts() == ("intranet.corp.local", "10.0.0.5")
    assert allowlist.find("intranet.corp.local").ports == (443,)
    assert allowlist.find("10.0.0.5").ping is False


def test_leitura_de_lista_simples_em_json(tmp_path: Path) -> None:
    caminho = tmp_path / ALLOWLIST_FILENAME
    caminho.write_text(json.dumps(["servidor.corp.local"]), encoding="utf-8")

    allowlist = load_allowlist(caminho)
    assert allowlist.hosts() == ("servidor.corp.local",)
    assert allowlist.find("servidor.corp.local").ports == DEFAULT_PORTS


def test_destino_invalido_e_descartado_com_aviso(tmp_path: Path) -> None:
    caminho = tmp_path / ALLOWLIST_FILENAME
    caminho.write_text(
        json.dumps({"targets": [{"host": "servidor ok"}, {"host": "10.0.0.5"}]}),
        encoding="utf-8",
    )

    allowlist = load_allowlist(caminho)
    assert allowlist.hosts() == ("10.0.0.5",)
    assert allowlist.warnings


def test_porta_fora_da_faixa_e_recusada(tmp_path: Path) -> None:
    caminho = tmp_path / ALLOWLIST_FILENAME
    caminho.write_text(
        json.dumps({"targets": [{"host": "servidor.local", "ports": [70000]}]}),
        encoding="utf-8",
    )

    allowlist = load_allowlist(caminho)
    assert allowlist.targets == ()
    assert allowlist.warnings


def test_limite_de_portas_por_destino(tmp_path: Path) -> None:
    portas = list(range(1, MAX_PORTS_PER_TARGET + 2))
    caminho = tmp_path / ALLOWLIST_FILENAME
    caminho.write_text(
        json.dumps({"targets": [{"host": "servidor.local", "ports": portas}]}),
        encoding="utf-8",
    )

    allowlist = load_allowlist(caminho)
    assert allowlist.targets == ()
    assert allowlist.warnings


def test_limite_de_destinos(tmp_path: Path) -> None:
    destinos = [{"host": f"servidor{indice}.local"} for indice in range(MAX_TARGETS + 3)]
    caminho = tmp_path / ALLOWLIST_FILENAME
    caminho.write_text(json.dumps({"targets": destinos}), encoding="utf-8")

    allowlist = load_allowlist(caminho)
    assert len(allowlist.targets) == MAX_TARGETS
    assert allowlist.warnings


def test_gravacao_e_releitura_preservam_a_lista(tmp_path: Path) -> None:
    caminho = tmp_path / ALLOWLIST_FILENAME
    save_allowlist(
        [
            AllowedTarget(host="intranet.corp.local", ports=(443,), description="Portal"),
            AllowedTarget(host="10.0.0.5", ports=(3389,), ping=False),
        ],
        caminho,
    )

    allowlist = load_allowlist(caminho)
    assert allowlist.hosts() == ("intranet.corp.local", "10.0.0.5")
    assert allowlist.find("intranet.corp.local").description == "Portal"
    assert allowlist.find("10.0.0.5").ping is False
    assert allowlist.find("10.0.0.5").ports == (3389,)


def test_gravacao_substitui_o_arquivo_de_forma_atomica(tmp_path: Path) -> None:
    caminho = tmp_path / ALLOWLIST_FILENAME
    save_allowlist([AllowedTarget(host="a.local")], caminho)
    save_allowlist([AllowedTarget(host="b.local")], caminho)

    allowlist = load_allowlist(caminho)
    assert allowlist.hosts() == ("b.local",)
    assert not (tmp_path / "allowed_targets.json.tmp").exists()


def test_consulta_de_destino_inexistente() -> None:
    allowlist = TargetAllowlist(targets=(AllowedTarget(host="a.local"),))
    assert allowlist.allows("a.local") is True
    assert allowlist.allows("b.local") is False
    assert allowlist.find("b.local") is None


def test_sintaxe_de_host() -> None:
    assert is_valid_host("servidor.corp.local") is True
    assert is_valid_host("10.0.0.5") is True
    assert is_valid_host("host-1") is True
    assert is_valid_host("") is False
    assert is_valid_host("host com espaco") is False
    assert is_valid_host("host; DROP TABLE") is False
    assert is_valid_host("*.corp.local") is False
    assert is_valid_host("10.0.0.0/24") is False
    assert is_valid_host("http://servidor") is False
    assert is_valid_host("a" * 254) is False


def test_deteccao_de_ip_literal() -> None:
    assert is_ip_literal("10.0.0.5") is True
    assert is_ip_literal("servidor.local") is False
    assert is_ip_literal("999.0.0.1") is False


def test_caminho_padrao_respeita_a_variavel_de_ambiente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = tmp_path / "custom.json"
    monkeypatch.setenv("DESKGUARD_ALLOWED_TARGETS_FILE", str(destino))
    assert default_allowlist_path() == destino


def test_erro_de_allowlist_e_um_value_error() -> None:
    assert issubclass(AllowlistError, ValueError)
