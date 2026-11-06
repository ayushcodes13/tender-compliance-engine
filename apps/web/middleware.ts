import { NextResponse, type NextRequest } from "next/server";
import { applicationAccessResponse, checkApplicationAccess } from "./app/access-control";

export function middleware(request: NextRequest) {
  const decision = checkApplicationAccess(
    request.headers.get("authorization"),
    process.env.APP_ACCESS_PASSWORD,
    process.env.NODE_ENV,
  );
  if (decision === "allow") return NextResponse.next();
  return applicationAccessResponse(decision);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
