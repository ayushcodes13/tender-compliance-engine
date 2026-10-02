"""Vendor specification extraction package (CP52).

Exports :class:`VendorSpecService` for extracting and listing structured
vendor specifications from accepted OEM evidence.
"""

from tender_compliance_api.vendor_spec.service import VendorSpecService

__all__ = ["VendorSpecService"]
