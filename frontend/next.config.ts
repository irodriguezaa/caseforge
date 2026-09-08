import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  basePath: "/qcpulse",
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async redirects() {
    return [
      { source: "/", destination: "/qcpulse", basePath: false, permanent: false },
      { source: "/login", destination: "/qcpulse/login", basePath: false, permanent: false },
    ];
  },
};

export default nextConfig;
