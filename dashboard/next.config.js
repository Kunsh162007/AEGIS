/** @type {import('next').NextConfig} */
const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// In production we export the dashboard to static files (`out/`) and let the
// FastAPI backend serve them on the same origin — one service, one URL, no CORS.
// Set STATIC_EXPORT=1 for that build (the Dockerfile does). Locally (dev), we
// instead proxy /api/* to the separate uvicorn backend.
const isExport = process.env.STATIC_EXPORT === "1";

const nextConfig = isExport
  ? {
      output: "export",
      images: { unoptimized: true },
    }
  : {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
      },
    };

module.exports = nextConfig;
