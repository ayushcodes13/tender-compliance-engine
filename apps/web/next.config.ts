import type { NextConfig } from "next";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
  async redirects() {
    // The simulated sign-in/sign-up forms were removed. Keep the old URLs
    // resolving so existing bookmarks and links land on the access page
    // instead of a 404.
    return [
      { source: "/sign-in", destination: "/access", permanent: true },
      { source: "/sign-up", destination: "/access", permanent: true },
    ];
  },
};

export default nextConfig;
