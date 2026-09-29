# Security Model

Tender and OEM documents may contain confidential commercial and technical information. Uploaded content is also untrusted input.

## Main threats

### Tenant data leakage

Risk: one organization reads another organization's projects or documents.

Controls:

- organization-scoped authorization on every query
- object-storage keys scoped by organization/project
- deny-by-default API authorization
- integration tests for cross-tenant access

### Malicious uploads

Risk: malformed PDFs, decompression bombs, malware, parser exploitation.

Controls:

- allowlisted MIME/file signatures
- file-size/page-count limits
- malware scanning in production
- sandbox/isolated document-processing workers
- processing timeouts and resource limits
- never execute embedded document code/macros

### Prompt injection in documents

Risk: document text attempts to override extraction/reasoning instructions.

Controls:

- treat document content strictly as data
- system/app instructions remain out-of-band
- structured schemas and validators
- no tool execution based on document instructions
- explicit provenance for model outputs

### Secret exposure

Controls:

- `.env` is ignored
- secret manager in deployed environments
- no provider keys in logs/prompts/fixtures
- rotate leaked keys immediately

### LLM provider confidentiality

Controls:

- select provider/account settings appropriate for confidential documents
- document retention/training settings
- minimize payloads where possible
- record provider/model metadata for audit
- offer provider abstraction so deployments can change vendors

### Inaccurate or fabricated output

This is a security/trust issue, not only a quality issue.

Controls:

- source-preserving extraction
- schema validation
- human review states
- exact vs approximate citation flag
- deterministic logic for later numerical comparisons
- evaluation gates for false extraction/citation/compliance

## Data retention

The product should support configurable retention and hard deletion of:

- original uploads
- derived page assets
- OCR/parser output
- embeddings later in Phase 2
- exports

Audit retention may require a distinct policy from document-content retention.

## Logging

Log identifiers, states, provider versions, latency, and error metadata. Avoid logging full tender/OEM document bodies unless explicitly required for a controlled debugging workflow.
