import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<Response> {
  const { path } = await params;
  const target = `${BACKEND_URL.replace(/\/$/, "")}/${path
    .map((segment) => encodeURIComponent(segment))
    .join("/")}${request.nextUrl.search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  try {
    let upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      duplex: hasBody ? "half" : undefined,
      redirect: "manual",
      cache: "no-store",
    } as RequestInit);

    // FastAPI may redirect a route to its canonical trailing-slash path. The
    // browser must never follow that Location to BACKEND_URL directly: doing
    // so leaks the internal origin and fails CORS. Follow same-backend GET or
    // HEAD redirects inside the proxy. Never replay a mutation body.
    const location = upstream.headers.get("location");
    const redirectStatuses = [301, 302, 303, 307, 308];
    if (
      location &&
      redirectStatuses.includes(upstream.status)
    ) {
      const redirectUrl = new URL(location, target);
      const backendOrigin = new URL(BACKEND_URL).origin;
      if (redirectUrl.origin === backendOrigin) {
        if (request.method !== "GET" && request.method !== "HEAD") {
          return Response.json(
            { detail: "The upstream service redirected a write request. Please retry." },
            { status: 502 }
          );
        }
        upstream = await fetch(redirectUrl, {
          method: request.method,
          headers,
          redirect: "manual",
          cache: "no-store",
        });
        const followUpLocation = upstream.headers.get("location");
        if (
          followUpLocation &&
          redirectStatuses.includes(upstream.status) &&
          new URL(followUpLocation, redirectUrl).origin === backendOrigin
        ) {
          return Response.json(
            { detail: "The upstream service returned too many redirects. Please retry." },
            { status: 502 }
          );
        }
      }
    }

    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.delete("content-encoding");
    responseHeaders.delete("content-length");

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      {
        detail:
          "The Tender Compliance service is temporarily unavailable. Please retry shortly.",
      },
      { status: 502 }
    );
  }
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
};
