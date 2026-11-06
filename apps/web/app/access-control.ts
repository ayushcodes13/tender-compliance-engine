const ACCESS_USERNAME = "tender";

function constantTimeEqual(left: string, right: string): boolean {
  const length = Math.max(left.length, right.length);
  let difference = left.length ^ right.length;
  for (let index = 0; index < length; index += 1) {
    difference |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return difference === 0;
}

function decodeBasicCredentials(value: string | null): { username: string; password: string } | null {
  if (!value) return null;
  const match = /^Basic\s+([A-Za-z0-9+/]+={0,2})$/i.exec(value.trim());
  if (!match) return null;
  try {
    const binary = atob(match[1]);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const separator = decoded.indexOf(":");
    if (separator < 0) return null;
    return { username: decoded.slice(0, separator), password: decoded.slice(separator + 1) };
  } catch {
    return null;
  }
}

export type AccessDecision = "allow" | "unauthorized" | "misconfigured";

export function checkApplicationAccess(
  authorization: string | null,
  configuredPassword: string | undefined,
  environment: string | undefined,
): AccessDecision {
  if (!configuredPassword) return environment === "production" ? "misconfigured" : "allow";
  const credentials = decodeBasicCredentials(authorization);
  if (!credentials) return "unauthorized";
  const usernameMatches = constantTimeEqual(credentials.username, ACCESS_USERNAME);
  const passwordMatches = constantTimeEqual(credentials.password, configuredPassword);
  return usernameMatches && passwordMatches ? "allow" : "unauthorized";
}

export function applicationAccessResponse(decision: Exclude<AccessDecision, "allow">): Response {
  if (decision === "misconfigured") {
    return new Response("Application access is not configured. Set APP_ACCESS_PASSWORD before serving production traffic.\n", {
      status: 503,
      headers: { "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return new Response("Authentication required.\n", {
    status: 401,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "text/plain; charset=utf-8",
      "WWW-Authenticate": 'Basic realm="Tender Compliance Engine", charset="UTF-8"',
    },
  });
}
