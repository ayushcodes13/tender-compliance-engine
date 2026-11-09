export const MAX_FILE_BYTES = 4 * 1024 * 1024;
export const LOCAL_MAX_FILE_BYTES = 32 * 1024 * 1024;

/** Resolve the limit compiled into the client bundle by next.config.ts. */
export function resolveClientMaxFileBytes(
  configuredValue = process.env.NEXT_PUBLIC_MAX_FILE_BYTES,
  nodeEnvironment = process.env.NODE_ENV,
): number {
  const configured = Number(configuredValue);
  if (Number.isSafeInteger(configured) && configured > 0) return configured;
  if (nodeEnvironment !== "production") return LOCAL_MAX_FILE_BYTES;
  return MAX_FILE_BYTES;
}

export function resolveMaxFileBytes(env: NodeJS.ProcessEnv = process.env): number {
  if (env.MAX_FILE_BYTES) {
    const parsed = Number(env.MAX_FILE_BYTES);
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }
  // Hosted Vercel environments are bounded to 4 MB due to serverless payload limits.
  // Local development / on-premise allows larger tenders up to 32 MB (supporting 7 MB+ PDFs).
  if (env.VERCEL === "1" || env.VERCEL_ENV) {
    return MAX_FILE_BYTES;
  }
  return LOCAL_MAX_FILE_BYTES;
}
