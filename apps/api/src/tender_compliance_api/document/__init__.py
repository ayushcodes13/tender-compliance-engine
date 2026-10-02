"""Document processing domain.

Import `DocumentService` and domain errors from `document.service` directly.
The package initializer stays side-effect free so importing a document submodule
does not eagerly import the full orchestration service.
"""
