"""Reusable authorization context.

``AuthContext`` is the single, shared tenant-authorization object that
every Phase-1 service and route receives.  It carries the *resolved* actor
and organization — never a browser-supplied ID that has not been verified
against the membership table.

Guardrail (AGENTS.md / CP08): never trust an organization ID supplied by
the browser without verifying membership.  This context is the enforcement
point: its ``organization_id`` always comes from a verified membership, not
from a request parameter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthContext:
    """Immutable, resolved authorization context for a single request.

    Attributes:
        actor_id: The UUID of the authenticated user (never None for a
            resolved context).
        organization_id: The verified tenant scope.  All queries in the
            request must be filtered by this value.
        roles: The set of roles the actor holds within ``organization_id``.
    """

    actor_id: uuid.UUID
    organization_id: uuid.UUID
    roles: frozenset[str]
