"""Auth request-context boundary and dev-mode identity resolver.

The single ``resolve_auth_context`` function is the entry point for turning
a request into a verified :class:`AuthContext`.  All later services and
routes depend on this — never on raw browser-supplied IDs.

Dev-mode identity (``app_env == "development"``) reads identity from
``X-Dev-User-Id`` / ``X-Dev-Organization-Id`` headers for local development
only.  Production deployments will plug in a real auth provider (OIDC/JWT)
but keep the same ``AuthContext`` output shape.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.config import get_settings
from tender_compliance_api.db.models import Membership, Organization, User

# Dev-mode identity headers (development-only).
DEV_USER_HEADER: Final = "x-dev-user-id"
DEV_ORG_HEADER: Final = "x-dev-organization-id"

# Constrained set of roles a membership may hold.
ROLE_OWNER: Final = "owner"
ROLE_ADMIN: Final = "admin"
ROLE_MEMBER: Final = "member"
ROLE_VIEWER: Final = "viewer"
VALID_ROLES: Final = frozenset(
    {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER}
)


async def resolve_auth_context(
    session: AsyncSession,
    headers: Mapping[str, str],
) -> AuthContext | None:
    """Resolve a verified authorization context from request headers.

    **Development mode** (``app_env == "development"``): reads
    ``X-Dev-User-Id`` and ``X-Dev-Organization-Id``, resolving/creating the
    ``User`` and ``Organization`` rows on the fly.  Membership is **verified**
    (not auto-created) — the browser-supplied org ID is never trusted
    without a confirmed membership row.

    **Non-development mode**: returns ``None`` (deny-by-default).  A real
    auth provider integration will replace this in a later checkpoint.

    Returns:
        An :class:`AuthContext` when a valid, verified actor is found,
        or ``None`` when the actor cannot be resolved (deny-by-default).
    """
    settings = get_settings()
    if settings.app_env != "development":
        # Dev-only identity mode: production requires a real auth provider.
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

    # --- Resolve or create the User (dev convenience) ---
    user = await session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            auth_provider="dev",
            auth_provider_user_id=str(user_id),
        )
        session.add(user)
        await session.flush()

    # --- Resolve or create the Organization (dev convenience) ---
    org = await session.get(Organization, org_id)
    if org is None:
        org = Organization(id=org_id, name=f"Dev Organization {org_id}")
        session.add(org)
        await session.flush()

    # --- Verify membership (never trust the header without this) ---
    result = await session.execute(
        select(Membership.role).where(
            Membership.organization_id == org_id,
            Membership.user_id == user_id,
        )
    )
    roles_raw = result.fetchall()
    if not roles_raw:
        return None  # No membership → deny

    roles = frozenset(row[0] for row in roles_raw)

    return AuthContext(
        actor_id=user_id,
        organization_id=org_id,
        roles=roles,
    )


def assert_valid_role(role: str) -> None:
    """Raise ``ValueError`` if *role* is not a recognized membership role."""
    if role not in VALID_ROLES:
        raise ValueError(f"Unknown role: {role!r}")
