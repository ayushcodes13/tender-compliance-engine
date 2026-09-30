"""Audit service package.

Provides a single reusable audit path (``AuditService``) so that every
mutation in a later checkpoint records a consistent, organization-scoped
event without duplicating log structure.
"""

from tender_compliance_api.audit.service import AuditService, write_audit_event

__all__ = ["AuditService", "write_audit_event"]
