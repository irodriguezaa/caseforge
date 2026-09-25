import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  basePath: "/qcpulse",
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  experimental: {
    serverActions: {
      bodySizeLimit: "25mb",
    },
    proxyClientMaxBodySize: "25mb",
  },
  async redirects() {
    return [
      { source: "/", destination: "/qcpulse", basePath: false, permanent: false },
      { source: "/login", destination: "/qcpulse/login", basePath: false, permanent: false },
    ];
  },
};

export default nextConfig;
