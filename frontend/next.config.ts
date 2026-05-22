import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const backendHost = process.env.API_PROXY_HOST || "127.0.0.1";
const backendPort = process.env.API_PROXY_PORT || "8011";
const apiProxyTarget = process.env.API_PROXY_TARGET || `http://${backendHost}:${backendPort}`;
const projectRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1:3005", "localhost:3005"],
  turbopack: {
    root: projectRoot,
  },
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
