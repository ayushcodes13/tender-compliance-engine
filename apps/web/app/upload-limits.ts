export const MAX_FILE_BYTES = 4 * 1024 * 1024;
export const LOCAL_MAX_FILE_BYTES = 32 * 1024 * 1024;

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
