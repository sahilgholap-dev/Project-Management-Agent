import type { NextConfig } from "next";

// All browser calls go to /api/* and are proxied to FastAPI, so the session
// cookie FastAPI sets lands on the frontend origin — no cookie re-plumbing.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Onboarding and monitoring cycles make several sequential LLM calls and
  // can run for minutes; the dev proxy's default ~30s timeout would cut the
  // socket (ECONNRESET) while FastAPI keeps working. 10 minutes covers the
  // slowest real onboarding run.
  experimental: {
    proxyTimeout: 600_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
