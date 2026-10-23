"""Fixtures compartilhadas pela suíte de testes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deskguard.api.app import create_app
from deskguard.config import Settings
from deskguard.storage.database import Database

# Importa os procedimentos sintéticos, registrando-os no catálogo.
import tests.fakes  # noqa: F401  pylint: disable=unused-import


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Configuração isolada por teste, apontando para um diretório temporário."""
    return Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "deskguard-test.db",
        host="127.0.0.1",
        port=8765,
        request_timeout_s=15.0,
        max_concurrent_executions=2,
    )


@pytest.fixture()
def database(settings: Settings) -> Database:
    db = Database(settings.database_path)
    db.create_all()
    yield db
    db.dispose()


@pytest.fixture()
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    """Cliente HTTP local.

    O ``base_url`` usa 127.0.0.1 porque a API recusa cabeçalhos ``Host`` não
    locais — proteção contra DNS rebinding.
    """
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


@pytest.fixture()
def csrf(client: TestClient) -> str:
    """Token anti-CSRF entregue na página inicial."""
    response = client.get("/")
    assert response.status_code == 200
    match = re.search(r'name="deskguard-csrf" content="([^"]+)"', response.text)
    assert match, "O token anti-CSRF não foi encontrado na página inicial."
    return match.group(1)
