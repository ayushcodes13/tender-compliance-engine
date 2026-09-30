"""FastAPI dependency that resolves the authorization context.

Routes inject ``get_auth_context`` to obtain a verified
:class:`AuthContext` or receive a ``401 Unauthorized`` — there is no path
that bypasses verification.
"""

from __future__ import annotations

from typing import Final

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.service import resolve_auth_context
from tender_compliance_api.db.session import get_session

# Value for the ``WWW-Authenticate`` response header on 401 responses.
WWW_AUTHENTICATE: Final = "bearer"


async def get_auth_context(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AuthContext:
    """FastAPI dependency: resolve and verify the request's auth context.

    Delegates to :func:`resolve_auth_context` (the reusable auth boundary).
    On failure a ``401`` is raised — deny-by-default.
    """
    auth = await resolve_auth_context(session, request.headers)
    if auth is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": WWW_AUTHENTICATE},
        )
    return auth
