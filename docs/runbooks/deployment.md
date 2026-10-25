# Deploy Tender Review on Vercel

The app root is `apps/web`; no API or worker service is deployed.

1. Connect `ayushcodes13/tender-compliance-engine` to Vercel.
2. Set the Root Directory to `apps/web` and use the Next.js preset.
3. Add `OPENAI_API_KEY` as a server-side Production environment variable. Add `OPENAI_BASE_URL` and `OPENAI_MODEL` only when using an OpenAI-compatible provider such as Azure.
4. Deploy the branch that contains the verified MVP.
5. Add `tender.devayushrout.me` under the Vercel project's Domains. Copy the exact DNS target Vercel displays.
6. In Namecheap Advanced DNS for `devayushrout.me`, create the record Vercel requested for host `tender` (usually a CNAME). Remove a conflicting record for the same host.
7. Wait for Vercel to report the domain as configured and verify the HTTPS URL loads.
8. Upload a fresh text-based sample tender through that HTTPS URL, inspect cited pages and highlights, then download and inspect the DOCX.

The user authorized the model credential as a server-only environment variable. Never put it in a `NEXT_PUBLIC_*` variable or commit it to the repository.

This is a small single-user demo. It does not provide accounts, persistent storage, hosted OCR, tenant isolation, or a completeness guarantee. For local OCR only, install Tesseract 5 and the required language data; set `TESSERACT_BINARY` and `TESSERACT_LANG` in the local environment if auto-detection or the English default is not suitable. OCR-derived evidence remains approximate and needs human inspection. Do not upload confidential tenders to the hosted preview unless access controls and document handling have been agreed separately.

Use Node.js 22.13+ for local work and Node.js 22 for CI/deployment. Before deploying a release, run `make web-test`, `make web-typecheck`, `make web-build`, and `make web-test-pipeline`. The pipeline test uses a scripted provider and synthetic documents; perform a separate real-model upload/review/export check on the intended deployment. The local client-tender check does not establish hosted performance or runtime limits.

Grouped source tables can use different verified column maps and retain their source annexure/equipment context. Unsupported geometry uses general extraction, and image/crop fallback still may require separate processing for incompatible visible layouts. PDF exports load the bundled DejaVu Sans font from the same origin; unsupported characters stop PDF creation and offer DOCX/Excel rather than silently dropping text.
