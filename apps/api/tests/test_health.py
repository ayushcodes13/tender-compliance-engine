from fastapi.testclient import TestClient

from tender_compliance_api.main import app

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
    assert payload["components"]["object_storage"] == "ready"
    assert payload["components"]["malware_scanner"] == "ready"
