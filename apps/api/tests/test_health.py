from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tender_compliance_api.main import app
from tender_compliance_api.queue.redis import RedisQueueAdapter
from tender_compliance_api.routes import health as health_module
from tender_compliance_api.routes.uploads import get_queue_adapter

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "tender-compliance-api",
    }


def test_ready_reports_components() -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["service"] == "tender-compliance-api"
    assert payload["components"]["database"] == "ready"
    assert payload["components"]["queue"] == "ready"
    assert payload["components"]["worker"] == "development"
    assert payload["components"]["object_storage"] == "ready"
    assert payload["components"]["malware_scanner"] == "ready"


@pytest.mark.parametrize(
    ("worker_alive", "expected_status", "expected_component"),
    [
        (True, 200, "ready"),
        (False, 503, "unavailable"),
    ],
)
def test_production_readiness_requires_worker_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    worker_alive: bool,
    expected_status: int,
    expected_component: str,
) -> None:
    class StubRedisQueue(RedisQueueAdapter):
        async def size(self, queue: str) -> int:
            return 0

        async def worker_ready(self) -> bool:
            return worker_alive

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        health_module,
        "get_settings",
        lambda: SimpleNamespace(is_production=True, openai_api_key="configured"),
    )
    app.dependency_overrides[get_queue_adapter] = StubRedisQueue
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.pop(get_queue_adapter, None)

    assert response.status_code == expected_status
    assert response.json()["components"]["worker"] == expected_component
