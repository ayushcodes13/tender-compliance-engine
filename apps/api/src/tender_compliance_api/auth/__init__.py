"""Authentication context package.

Provides the single reusable authorization context (AuthContext) and the
auth request-context boundary (auth service + FastAPI dependency) for
later services.
"""

from tender_compliance_api.auth.context import AuthContext

__all__ = ["AuthContext"]
