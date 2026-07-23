import type { NextConfig } from "next";

// All browser calls go to /api/* and are proxied to FastAPI, so the session
// cookie FastAPI sets lands on the frontend origin — no cookie re-plumbing.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
