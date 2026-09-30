"""API-level tests for the project lifecycle routes (CP10).

These tests exercise the full HTTP request/response cycle via FastAPI's
TestClient, covering auth resolution, service delegation, exception-to-HTTP
status mapping, and tenant isolation.
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from tender_compliance_api.db.models import (
    Membership,
    Organization,
    User,
)
from tender_compliance_api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _setup_identity(session_cm) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a committed org + user + membership; return (user_id, org_id)."""

    async def _create() -> tuple[uuid.UUID, uuid.UUID]:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=org_id, name=f"Test Org {org_id}"))
            session.add(
                User(
                    id=user_id,
                    auth_provider="dev",
                    auth_provider_user_id=str(user_id),
                )
            )
            session.add(
                Membership(organization_id=org_id, user_id=user_id, role="owner")
            )
            await session.commit()
        return user_id, org_id

    return asyncio.run(_create())


def _create_project(session_cm, name: str = "Test Project") -> tuple[str, uuid.UUID, uuid.UUID]:
    """Create a project via the API and return (project_id_str, user_id, org_id)."""
    user_id, org_id = _setup_identity(session_cm)
    res = client.post(
        "/projects",
        json={"name": name},
        headers=_headers(user_id, org_id),
    )
    assert res.status_code == 201, res.text
    return res.json()["id"], user_id, org_id


# ---------------------------------------------------------------------------
# POST /projects
# ---------------------------------------------------------------------------


def test_create_project(session_cm):
    user_id, org_id = _setup_identity(session_cm)
    response = client.post(
        "/projects",
        json={"name": "Test Project"},
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Project"
    assert data["status"] == "draft"
    assert data["external_tender_id"] is None
    assert data["organization_id"] == str(org_id)
    assert data["created_by"] == str(user_id)
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_project_with_external_tender_id(session_cm):
    user_id, org_id = _setup_identity(session_cm)
    response = client.post(
        "/projects",
        json={"name": "Tender XYZ", "external_tender_id": "EXT-001"},
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 201
    assert response.json()["external_tender_id"] == "EXT-001"


def test_create_project_requires_auth():
    response = client.post("/projects", json={"name": "Test"})
    assert response.status_code == 401


def test_create_project_validation_error(session_cm):
    user_id, org_id = _setup_identity(session_cm)
    response = client.post(
        "/projects",
        json={"name": ""},  # empty name violates min_length=1
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /projects
# ---------------------------------------------------------------------------


def test_list_projects(session_cm):
    user_id, org_id = _setup_identity(session_cm)
    for name in ("Alpha", "Beta"):
        client.post(
            "/projects",
            json={"name": name},
            headers=_headers(user_id, org_id),
        )
    response = client.get("/projects", headers=_headers(user_id, org_id))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {p["name"] for p in data} == {"Alpha", "Beta"}


def test_list_projects_requires_auth():
    response = client.get("/projects")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /projects/{id}
# ---------------------------------------------------------------------------


def test_get_project(session_cm):
    project_id, user_id, org_id = _create_project(session_cm, "Get Me")
    response = client.get(
        f"/projects/{project_id}",
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Get Me"
    assert data["id"] == project_id


def test_get_project_not_found(session_cm):
    user_id, org_id = _setup_identity(session_cm)
    response = client.get(
        f"/projects/{uuid.uuid4()}",
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 404


def test_get_project_cross_tenant(session_cm):
    # Org A creates a project
    project_id_a, user_a, org_a = _create_project(session_cm, "Org A Project")
    # Org B tries to read it
    user_b, org_b = _setup_identity(session_cm)
    response = client.get(
        f"/projects/{project_id_a}",
        headers=_headers(user_b, org_b),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /projects/{id}  (rename)
# ---------------------------------------------------------------------------


def test_rename_project(session_cm):
    project_id, user_id, org_id = _create_project(session_cm, "Old Name")
    response = client.patch(
        f"/projects/{project_id}",
        json={"name": "New Name"},
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_rename_project_validation_error(session_cm):
    project_id, user_id, org_id = _create_project(session_cm, "Test")
    response = client.patch(
        f"/projects/{project_id}",
        json={"name": ""},
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 422


def test_rename_archived_project_rejected(session_cm):
    project_id, user_id, org_id = _create_project(session_cm, "Test")
    client.post(
        f"/projects/{project_id}/archive",
        headers=_headers(user_id, org_id),
    )
    response = client.patch(
        f"/projects/{project_id}",
        json={"name": "New"},
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST /projects/{id}/archive
# ---------------------------------------------------------------------------


def test_archive_project(session_cm):
    project_id, user_id, org_id = _create_project(session_cm, "Test")
    response = client.post(
        f"/projects/{project_id}/archive",
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "archived"


def test_archive_already_archived_rejected(session_cm):
    project_id, user_id, org_id = _create_project(session_cm, "Test")
    first = client.post(
        f"/projects/{project_id}/archive",
        headers=_headers(user_id, org_id),
    )
    assert first.status_code == 200
    second = client.post(
        f"/projects/{project_id}/archive",
        headers=_headers(user_id, org_id),
    )
    assert second.status_code == 400


def test_archive_project_not_found(session_cm):
    user_id, org_id = _setup_identity(session_cm)
    response = client.post(
        f"/projects/{uuid.uuid4()}/archive",
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /projects/{id}/reopen
# ---------------------------------------------------------------------------


def test_reopen_project(session_cm):
    project_id, user_id, org_id = _create_project(session_cm, "Test")
    client.post(
        f"/projects/{project_id}/archive",
        headers=_headers(user_id, org_id),
    )
    response = client.post(
        f"/projects/{project_id}/reopen",
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "draft"


def test_reopen_active_project_rejected(session_cm):
    project_id, user_id, org_id = _create_project(session_cm, "Test")
    response = client.post(
        f"/projects/{project_id}/reopen",
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 400


def test_reopen_project_not_found(session_cm):
    user_id, org_id = _setup_identity(session_cm)
    response = client.post(
        f"/projects/{uuid.uuid4()}/reopen",
        headers=_headers(user_id, org_id),
    )
    assert response.status_code == 404
