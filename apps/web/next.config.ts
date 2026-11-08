import type { NextConfig } from "next";
import { LOCAL_MAX_FILE_BYTES, MAX_FILE_BYTES } from "./app/upload-limits";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

const isHosted = Boolean(process.env.VERCEL === "1" || process.env.VERCEL_ENV);
const configuredFileLimit = Number(process.env.MAX_FILE_BYTES);
const clientMaxFileBytes = isHosted ? MAX_FILE_BYTES
  : Number.isSafeInteger(configuredFileLimit) && configuredFileLimit > 0 ? configuredFileLimit : LOCAL_MAX_FILE_BYTES;

const nextConfig: NextConfig = {
  env: { NEXT_PUBLIC_MAX_FILE_BYTES: String(clientMaxFileBytes) },
  reactStrictMode: true,
  // PDF.js resolves its Node fake worker relative to the installed module.
  // Bundling it into a Server Action breaks that dynamic worker import.
  serverExternalPackages: ["pdfjs-dist", "@napi-rs/canvas"],
  outputFileTracingIncludes: {
    "/*": [
      "./node_modules/@napi-rs/canvas/**/*",
      "./node_modules/pdfjs-dist/legacy/build/pdf.worker.mjs",
      "./node_modules/pdfjs-dist/standard_fonts/**/*",
      "./node_modules/pdfjs-dist/cmaps/**/*",
      "./node_modules/@napi-rs/canvas-linux-x64-gnu/**/*",
    ],
  },
  experimental: {
    // Keep the proxy buffer large enough for the bounded multipart upload path.
    // The route itself enforces the exact file plus multipart-envelope limit.
    middlewareClientMaxBodySize: "33mb",
    serverActions: { bodySizeLimit: isHosted ? "4.5mb" : "32mb" },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
