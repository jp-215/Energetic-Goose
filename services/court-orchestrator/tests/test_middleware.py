import logging
import os

import app.middleware.env_loader as env_loader
import pytest
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_env_loader_fails_fast_without_api_key(monkeypatch):
    monkeypatch.delenv("CANOPYWAVE_API_KEY", raising=False)
    monkeypatch.setattr(env_loader, "ENV_CANDIDATES", [])
    with pytest.raises(RuntimeError, match="CANOPYWAVE_API_KEY"):
        create_app()


def test_env_loader_populates_environ():
    app = create_app()  # real candidates: Demo/.env supplies the key
    assert os.environ.get("CANOPYWAVE_API_KEY")
    assert app.state.middleware_installed["env_loader"] is True
    assert "CANOPYWAVE_API_KEY" in app.state.env_sources


def test_full_chain_installs_in_order():
    app = create_app()
    assert app.state.middleware_installed == {
        "env_loader": True,
        "cors": True,
        "datacat": True,
        "preflight": True,
    }


def test_cors_allows_frontend_origin():
    client = TestClient(create_app())
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_preflight_blocks_missing_prerequisite():
    from app.middleware import preflight

    bare_app = FastAPI()
    bare_app.state.middleware_installed = {"env_loader": True, "cors": True}  # no datacat
    with pytest.raises(RuntimeError, match="datacat"):
        preflight.install(bare_app)


def test_datacat_logs_banner_and_requests(caplog):
    app = create_app()
    with caplog.at_level(logging.INFO, logger="datacat"):
        with TestClient(app) as client:  # context manager triggers startup events
            client.get("/api/health")
    messages = [record.getMessage() for record in caplog.records]
    assert any("court-orchestrator launched" in m for m in messages)
    assert any("GET /api/health -> 200" in m for m in messages)
    # The banner must never leak the raw API key.
    raw_key = os.environ["CANOPYWAVE_API_KEY"]
    assert all(raw_key not in m for m in messages)
