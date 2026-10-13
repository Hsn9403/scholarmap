import type { NextConfig } from "next";

// Flask API — override when the backend does not run next to the frontend
const API_URL = process.env.SCHOLARMAP_API_URL ?? "http://localhost:5001";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/graphs/:path*", destination: `${API_URL}/graphs/:path*` },
      { source: "/static/:path*", destination: `${API_URL}/static/:path*` },
    ];
  },
};

export default nextConfig;
