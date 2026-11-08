# Free preview hosting for larger PDFs

The optional Render Blueprint in `render.yaml` defines one **Free** Node/Docker web service, with no database, object store, disk, queue, or worker. It sets a 32 MiB PDF limit and disables automatic deploys. The Docker image installs the existing local OCR tools and runs the current Next.js application. No service is created by this repository change; an owner must explicitly import the Blueprint and supply secrets.

## Setup

1. Import this repository as a Render Blueprint and confirm the service plan remains `Free` before creating it.
2. Set a strong `APP_ACCESS_PASSWORD` and provide `OPENAI_API_KEY` only through Render's secret environment-variable UI. Do not commit either value.
3. Leave auto-deploy disabled until a reviewed commit is deliberately deployed.
4. Keep tender review data in the operator's browser. The free service has ephemeral server storage; do not write uploaded PDFs or review state to the container filesystem.

## Limits and security

- The application enforces a 32 MiB file limit plus at most 256 KiB for multipart framing. The limit is checked while streaming the request before `formData()` buffers it.
- Next.js's separate middleware request clone buffer is configured to 33 MB. Without this setting, the framework only exposes the first 10 MB to the route, even when the route's own streaming limit is larger. See the [Next.js 15 configuration reference](https://nextjs.org/docs/15/app/api-reference/config/next-config-js/middlewareClientMaxBodySize).
- The exact Dockerfile was built locally with the legacy Docker builder and started on loopback with synthetic Basic Auth and an empty model key. A synthetic 32 MiB, one-page PDF passed Next middleware and bounded multipart parsing, reached PDF reading, and stopped at the missing-credential guard. A 32 MiB + 1 byte PDF was rejected before PDF parsing. Both requests made no model call. The image reports Tesseract 5.3.0 and Poppler `pdftoppm` 22.12.0. This validates the app and local container path, not the Render network edge or its deployment architecture.
- Render Free web services may sleep after 15 minutes idle, restart, have only one small instance, and have ephemeral filesystems. This is a preview host, not a production availability or retention guarantee.
- Render documents a free-service plan but does not publish a specific maximum inbound HTTP request size in the current web-service/free-tier documentation. The app-level 32 MiB bound is verified locally; the provider edge limit still needs a single non-sensitive 32 MiB deployment smoke test before claiming hosted acceptance.
- The free service requires internet access to the configured model endpoint. A real analysis can incur model-provider charges; this setup does not make model calls free. No test or deploy in this change calls the model or creates a hosting service.
- Vercel Functions retain their documented 4.5 MB request/response payload ceiling, so this 32 MiB path applies only to a compatible Node host such as the configured Render preview, not the existing Vercel deployment.
- Do not use the free preview for confidential customer documents without an explicit privacy/security review. Shared Basic Auth is not user-level authentication, and browser saves are local to one browser profile.
