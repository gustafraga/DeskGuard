"""Testes de integração da API local.

Cobrem o caminho completo: interface → API → serviço de execução → coletores
→ persistência → relatório.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient


def _aguardar(client: TestClient, execution_id: str, timeout: float = 30.0) -> dict:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        response = client.get(f"/api/executions/{execution_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] not in ("queued", "running"):
            return payload
        time.sleep(0.1)
    raise AssertionError(f"A execução {execution_id} não concluiu em {timeout}s.")


def test_pagina_inicial_e_servida_com_token(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "DeskGuard" in response.text
    assert 'name="deskguard-csrf"' in response.text


def test_host_nao_local_e_recusado(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Host": "atacante.example.com"})
    assert response.status_code == 403
    assert "Host" in response.json()["detail"]


def test_health_retorna_estado_do_ambiente(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"]
    assert payload["powershell_available"] is True
    assert payload["procedures"] >= 1


def test_catalogo_lista_o_procedimento_padrao(client: TestClient) -> None:
    response = client.get("/api/procedures")
    assert response.status_code == 200
    payload = response.json()
    identificadores = [item["id"] for item in payload["procedures"]]
    assert "system.overview" in identificadores
    assert payload["count"] == len(payload["procedures"])
    assert any(categoria["id"] == "Sistema" for categoria in payload["categories"])


def test_detalhe_do_procedimento_explica_o_que_faz(client: TestClient) -> None:
    response = client.get("/api/procedures/system.overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert payload["steps"]
    assert payload["risk_notes"]
    assert payload["prerequisites"]


def test_procedimento_inexistente_retorna_404(client: TestClient) -> None:
    response = client.get("/api/procedures/nao.existe")
    assert response.status_code == 404


def test_execucao_sem_token_csrf_e_recusada(client: TestClient) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {}},
    )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_execucao_com_token_csrf_invalido_e_recusada(client: TestClient) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {}},
        headers={"X-DeskGuard-CSRF": "token-invalido"},
    )
    assert response.status_code == 403


def test_execucao_completa_e_persistida(client: TestClient, csrf: str) -> None:
    response = client.post(
        "/api/executions",
        json={
            "procedure_id": "test.fake.readonly",
            "params": {"factor": 5},
            "mode": "live",
        },
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 202
    execution_id = response.json()["execution_id"]

    payload = _aguardar(client, execution_id)
    assert payload["status"] == "completed"
    assert payload["outcome"] == "healthy"
    assert payload["procedure_id"] == "test.fake.readonly"
    assert payload["params"] == {"factor": 5}
    assert payload["duration_ms"] is not None
    assert payload["steps"][0]["evidence"]["factor"] == 5
    assert payload["presentation"]["summary"]["counts"]["passed"] == 1
    assert payload["steps"][0]["technical_sections"][0]["title"] == "Informações"


def test_execucao_de_procedimento_inexistente_retorna_404(
    client: TestClient, csrf: str
) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "nao.existe", "params": {}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 404


def test_execucao_com_parametro_invalido_retorna_422(
    client: TestClient, csrf: str
) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {"factor": 999}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 422
    assert "factor" in response.json()["detail"]


def test_execucao_com_parametro_desconhecido_retorna_422(
    client: TestClient, csrf: str
) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {"outro": 1}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 422


def test_procedimento_modificante_exige_aprovacao(client: TestClient, csrf: str) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.mutating", "params": {}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 403
    assert "confirmação" in response.json()["detail"].lower()


def test_procedimento_modificante_e_aceito_com_aprovacao(
    client: TestClient, csrf: str
) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.mutating", "params": {}, "approved": True},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 202
    payload = _aguardar(client, response.json()["execution_id"])
    assert payload["approval_granted"] is True


def test_execucao_em_modo_demonstracao_e_identificada(
    client: TestClient, csrf: str
) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "system.overview", "params": {}, "mode": "demo"},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 202
    payload = _aguardar(client, response.json()["execution_id"])

    assert payload["mode"] == "demo"
    assert payload["steps"], "a execução simulada deve produzir etapas"
    assert all(step["simulated"] is True for step in payload["steps"])
    assert any(
        step["evidence"].get("simulated") is True for step in payload["steps"]
    )


def test_relatorio_e_gerado_e_editavel(client: TestClient, csrf: str) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    execution_id = response.json()["execution_id"]
    _aguardar(client, execution_id)

    report = client.get(f"/api/executions/{execution_id}/report")
    assert report.status_code == 200
    payload = report.json()
    assert payload["editable"] is True
    assert "Identificador da execução" in payload["markdown"]
    assert execution_id in payload["markdown"]
    assert payload["presentation"]["summary"]["counts"]["passed"] == 1
    assert "Dados Brutos (Dev)" in payload["markdown"]
    assert "Dados Brutos" not in payload["copy_markdown"]


def test_exportacao_respeita_o_texto_editado(client: TestClient, csrf: str) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    execution_id = response.json()["execution_id"]
    _aguardar(client, execution_id)

    export = client.post(
        f"/api/executions/{execution_id}/report/export",
        json={"format": "markdown", "edited_text": "Relatório revisado à mão."},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert export.status_code == 200
    assert export.text == "Relatório revisado à mão."
    assert "attachment" in export.headers.get("content-disposition", "")


def test_exportacao_exige_csrf(client: TestClient, csrf: str) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    execution_id = response.json()["execution_id"]
    _aguardar(client, execution_id)

    export = client.post(
        f"/api/executions/{execution_id}/report/export",
        json={"format": "markdown"},
    )
    assert export.status_code == 403


def test_historico_filtra_e_pagina(client: TestClient, csrf: str) -> None:
    client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {"factor": 3}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    _aguardar(client, (client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {"factor": 4}},
        headers={"X-DeskGuard-CSRF": csrf},
    ).json()["execution_id"]))

    response = client.get("/api/executions", params={"query": "Procedimento de teste"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert len(payload["executions"]) <= payload["total"]

    filtrado = client.get(
        "/api/executions", params={"procedure_id": "test.fake.readonly"}
    )
    assert filtrado.json()["total"] >= 2


def test_painel_calcula_indicadores(client: TestClient, csrf: str) -> None:
    client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    _aguardar(client, (client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {}},
        headers={"X-DeskGuard-CSRF": csrf},
    ).json()["execution_id"]))

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_executions"] >= 2
    assert payload["executions_24h"] >= 2
    assert "by_outcome" in payload


def test_catalogo_inclui_o_diagnostico_de_active_directory(
    client: TestClient,
) -> None:
    response = client.get("/api/procedures")
    assert response.status_code == 200
    procedural = {item["id"]: item for item in response.json()["procedures"]}
    assert "ad.self_status" in procedural
    assert procedural["ad.self_status"]["read_only"] is True
    assert procedural["ad.self_status"]["privilege"] == "user"


def test_rota_do_dashboard_expoe_conta_e_confianca_do_dominio(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deskguard.api.routes import system

    payload = {
        "generated_at": "2026-10-23T12:00:00+00:00",
        "mode": "live",
        "username": "tecnico.exemplo",
        "account": {
            "username": "tecnico.exemplo",
            "user_domain": "EMPRESA",
            "status": "pass",
            "severity": "info",
            "message": "Conta ativa, desbloqueada e com senha válida.",
            "enabled": True,
            "locked_out": False,
            "password_expired": False,
            "account_expiration_date": "2026-12-31T00:00:00",
            "days_until_expiration": 69,
            "last_logon_date": "2026-10-23T09:15:00",
        },
        "domain_trust": {
            "status": "warn",
            "severity": "high",
            "message": (
                "A confiança do computador com o domínio está quebrada. "
                "O reparo exige privilégios de administrador."
            ),
            "checked": True,
            "ok": False,
            "domain": "empresa.local",
        },
    }
    monkeypatch.setattr(
        system, "collect_self_status_summary", lambda **_: payload
    )

    response = client.get("/api/ad/self-status")

    assert response.status_code == 200
    body = response.json()
    assert body["account"]["enabled"] is True
    assert body["account"]["days_until_expiration"] == 69
    assert body["domain_trust"]["status"] == "warn"
    assert body["domain_trust"]["ok"] is False


def test_dashboard_renderiza_cards_minha_conta_e_confianca(
    client: TestClient,
) -> None:
    response = client.get("/static/js/views.js")
    assert response.status_code == 200
    script = response.text
    assert "Minha Conta" in script
    assert "Confiança do Domínio" in script
    assert "adSelfStatus" in script


def test_execucao_de_ad_self_status_em_modo_demonstracao(
    client: TestClient, csrf: str
) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "ad.self_status", "params": {}, "mode": "demo"},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 202
    payload = _aguardar(client, response.json()["execution_id"])

    assert payload["status"] == "completed"
    assert {step["check_id"] for step in payload["steps"]} == {
        "ad.account",
        "ad.domain_trust",
    }
    assert all(step["simulated"] is True for step in payload["steps"])


def test_auditoria_registra_a_execucao(client: TestClient, csrf: str) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": "test.fake.readonly", "params": {}},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    execution_id = response.json()["execution_id"]
    _aguardar(client, execution_id)

    auditoria = client.get("/api/audit")
    assert auditoria.status_code == 200
    eventos = auditoria.json()["events"]
    acoes = {evento["action"] for evento in eventos}
    assert "execution.started" in acoes
    assert "execution.finished" in acoes

    filtrada = client.get("/api/audit", params={"query": "execution.started"})
    assert filtrada.json()["count"] >= 1


def test_configuracoes_expoem_permissao_e_catalogo(client: TestClient) -> None:
    response = client.get("/api/settings")
    assert response.status_code == 200
    payload = response.json()
    assert "is_admin" in payload["privilege"]
    assert payload["catalog"]["count"] >= 1
    assert payload["settings"]["host"] == "127.0.0.1"


def test_configuracoes_expoem_a_lista_de_destinos_autorizados(
    client: TestClient, settings
) -> None:
    response = client.get("/api/settings")
    assert response.status_code == 200
    allowlist = response.json()["allowlist"]
    assert "targets" in allowlist
    assert "path" in allowlist
    assert allowlist["path"].endswith("allowed_targets.json")
    assert str(settings.data_dir) in allowlist["path"]


def test_configuracoes_expoem_a_disponibilidade_da_camada_desktop(
    client: TestClient,
) -> None:
    response = client.get("/api/settings")
    assert response.status_code == 200
    desktop = response.json()["desktop"]
    assert isinstance(desktop["available"], bool)
    if desktop["available"]:
        assert desktop["reason"] is None
    else:
        assert desktop["reason"]


def test_catalogo_inclui_rede_e_impressoras(client: TestClient) -> None:
    response = client.get("/api/procedures")
    assert response.status_code == 200
    payload = response.json()
    identificadores = {item["id"] for item in payload["procedures"]}
    assert {
        "network.configuration",
        "network.connectivity",
        "printers.status",
    } <= identificadores
    categorias = {categoria["id"] for categoria in payload["categories"]}
    assert {"Rede", "Impressoras"} <= categorias


def test_parametros_de_destino_sao_declarados_no_catalogo(
    client: TestClient,
) -> None:
    response = client.get("/api/procedures/network.connectivity")
    assert response.status_code == 200
    parametros = {param["name"]: param for param in response.json()["params"]}
    assert parametros["targets"]["type"] == "host_list"
    assert parametros["probe_timeout_s"]["default"] == 3


def test_destino_nao_autorizado_retorna_422(
    client: TestClient, csrf: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv(
        "DESKGUARD_ALLOWED_TARGETS_FILE", str(tmp_path / "allowed_targets.json")
    )
    response = client.post(
        "/api/executions",
        json={
            "procedure_id": "network.connectivity",
            "params": {"targets": ["8.8.8.8"]},
            "mode": "demo",
        },
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 422
    assert "autorizados" in response.json()["detail"].lower()


def test_destino_autorizado_e_aceito(
    client: TestClient, csrf: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    caminho = tmp_path / "allowed_targets.json"
    caminho.write_text(
        json.dumps({"targets": [{"host": "intranet.corp.local", "ports": [443]}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DESKGUARD_ALLOWED_TARGETS_FILE", str(caminho))

    response = client.post(
        "/api/executions",
        json={
            "procedure_id": "network.connectivity",
            "params": {"targets": ["intranet.corp.local"]},
            "mode": "demo",
        },
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 202
    payload = _aguardar(client, response.json()["execution_id"])
    assert payload["params"]["targets"] == ["intranet.corp.local"]
    assert all(step["simulated"] is True for step in payload["steps"])


@pytest.mark.parametrize(
    "procedure_id",
    ["network.configuration", "network.connectivity", "printers.status"],
)
def test_novos_procedimentos_rodam_em_modo_demonstracao(
    client: TestClient, csrf: str, procedure_id: str
) -> None:
    response = client.post(
        "/api/executions",
        json={"procedure_id": procedure_id, "params": {}, "mode": "demo"},
        headers={"X-DeskGuard-CSRF": csrf},
    )
    assert response.status_code == 202
    payload = _aguardar(client, response.json()["execution_id"])

    assert payload["status"] == "completed"
    assert payload["steps"], "a execução simulada deve produzir etapas"
    assert all(step["simulated"] is True for step in payload["steps"])
    assert any(
        step["evidence"].get("simulated") is True for step in payload["steps"]
    )


@pytest.mark.parametrize(
    "rota",
    ["/api/health", "/api/dashboard", "/api/procedures", "/api/executions", "/api/audit"],
)
def test_rotas_de_leitura_nao_exigem_csrf(client: TestClient, rota: str) -> None:
    assert client.get(rota).status_code == 200
