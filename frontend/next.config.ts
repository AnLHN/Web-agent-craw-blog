import type { NextConfig } from "next";

const backendHost = process.env.API_PROXY_HOST || "127.0.0.1";
const backendPort = process.env.API_PROXY_PORT || "8000";
const apiProxyTarget = process.env.API_PROXY_TARGET || `http://${backendHost}:${backendPort}`;

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiProxyTarget}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
