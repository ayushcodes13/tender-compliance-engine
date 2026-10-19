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

This is a small single-user demo. It does not provide accounts, persistent storage, OCR, tenant isolation, or a completeness guarantee. Do not upload confidential tenders unless access controls and document handling have been agreed separately.
