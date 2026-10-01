"""Object-key construction and scoping utilities (CP12).

Keys are structured so that the organization identifier is the first path
component, guaranteeing namespace isolation: two organizations can never
collide, even if they reuse the same project/document/version labels.

Key format::

    {org_id}/{project_id}[/{document_id}[/{version}]]/{object_uuid}{ext}

A UUID is always appended as the terminal component so that two files
with the same original filename never collide.
"""

from __future__ import annotations

import uuid
from pathlib import Path


def build_key(
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
    version: int | None = None,
    object_id: uuid.UUID | None = None,
    original_filename: str | None = None,
) -> str:
    """Build a scoped, collision-free object key.

    Args:
        org_id: Organization UUID (namespace root).
        project_id: Project UUID.
        document_id: Optional document UUID.
        version: Optional document version number.
        object_id: Optional pre-assigned object UUID.  If ``None`` a new
            UUID4 is generated.
        original_filename: Optional original filename whose extension
            is preserved on the terminal component.

    Returns:
        A key string like ``"org-uuid/proj-uuid/object-uuid.pdf"``.
    """
    oid = object_id if object_id is not None else uuid.uuid4()
    parts: list[str] = [str(org_id), str(project_id)]

    if document_id is not None:
        parts.append(str(document_id))
        if version is not None:
            parts.append(str(version))

    ext = ""
    if original_filename:
        ext = Path(original_filename).suffix.lower()

    parts.append(f"{oid}{ext}")
    return "/".join(parts)


def parse_key(key: str) -> str:
    """Return the key unchanged.

    Kept as a named function so callers have a single, documented place
    to extend key parsing when reverse-lookup (e.g. extracting org_id
    from a key) becomes necessary.
    """
    return key
