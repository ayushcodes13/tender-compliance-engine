"""Authentication request-context boundary.

Two deliberately small modes are supported:

* development_headers keeps the existing local/test identity headers and
  still verifies an existing membership.
* single_workspace bootstraps one configured owner/workspace. This makes a
  private beta deployment usable without a separate identity provider or
  manual database seeding.

Any other mode denies by default. A public multi-user deployment should replace
single_workspace with a real OIDC/JWT integration while keeping the same
AuthContext boundary.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.config import Settings, get_settings
from tender_compliance_api.db.models import Membership, Organization, User

DEV_USER_HEADER: Final = "x-dev-user-id"
DEV_ORG_HEADER: Final = "x-dev-organization-id"

ROLE_OWNER: Final = "owner"
ROLE_ADMIN: Final = "admin"
ROLE_MEMBER: Final = "member"
ROLE_VIEWER: Final = "viewer"
VALID_ROLES: Final = frozenset(
    {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER}
)


async def _single_workspace_context(
    session: AsyncSession, settings: Settings
) -> AuthContext | None:
    """Ensure and return the configured single-workspace owner identity."""
    try:
        user_id = uuid.UUID(settings.single_workspace_user_id)
        org_id = uuid.UUID(settings.single_workspace_org_id)
    except (TypeError, ValueError):
        return None

    user = await session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            auth_provider="single_workspace",
            auth_provider_user_id=str(user_id),
            full_name="Workspace Owner",
        )
        session.add(user)

    org = await session.get(Organization, org_id)
    if org is None:
        org = Organization(id=org_id, name=settings.single_workspace_org_name)
        session.add(org)

    await session.flush()

    membership_result = await session.execute(
        select(Membership).where(
            Membership.organization_id == org_id,
            Membership.user_id == user_id,
        )
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        session.add(
            Membership(
                organization_id=org_id,
                user_id=user_id,
                role=ROLE_OWNER,
            )
        )
        await session.flush()
        roles = frozenset({ROLE_OWNER})
    else:
        roles = frozenset({membership.role})

    return AuthContext(
        actor_id=user_id,
        organization_id=org_id,
        roles=roles,
    )


async def resolve_auth_context(
    session: AsyncSession,
    headers: Mapping[str, str],
) -> AuthContext | None:
    """Resolve a verified authorization context for one request."""
    settings = get_settings()

    if settings.auth_mode == "single_workspace":
        return await _single_workspace_context(session, settings)

    if settings.auth_mode != "development_headers" or settings.app_env != "development":
        return None

    user_id_str = headers.get(DEV_USER_HEADER)
    org_id_str = headers.get(DEV_ORG_HEADER)
    if not user_id_str or not org_id_str:
        return None

    try:
        user_id = uuid.UUID(user_id_str)
        org_id = uuid.UUID(org_id_str)
    except (ValueError, TypeError):
        return None

    user = await session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            auth_provider="dev",
            auth_provider_user_id=str(user_id),
        )
        session.add(user)
        await session.flush()

    org = await session.get(Organization, org_id)
    if org is None:
        org = Organization(id=org_id, name=f"Dev Organization {org_id}")
        session.add(org)
        await session.flush()

    result = await session.execute(
        select(Membership.role).where(
            Membership.organization_id == org_id,
            Membership.user_id == user_id,
        )
    )
    roles_raw = result.fetchall()
    if not roles_raw:
        return None

    return AuthContext(
        actor_id=user_id,
        organization_id=org_id,
        roles=frozenset(row[0] for row in roles_raw),
    )


def assert_valid_role(role: str) -> None:
    """Raise ValueError if role is not a recognized membership role."""
    if role not in VALID_ROLES:
        raise ValueError(f"Unknown role: {role!r}")
