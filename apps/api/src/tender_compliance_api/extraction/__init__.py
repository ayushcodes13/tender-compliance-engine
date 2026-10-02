"""Tender requirement extraction package.

Import concrete contracts and services from their defining modules (for example
`extraction.schema`, `extraction.adapter`, or `extraction.extractor`).

Keeping this package initializer intentionally light avoids importing benchmark,
evaluation, provider, and database-adjacent code whenever any extraction
submodule is imported.
"""
