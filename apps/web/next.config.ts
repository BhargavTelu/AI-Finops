import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    typedRoutes: true,
  },
  // Transpile Tremor — it ships ESM that Next.js needs to handle
  transpilePackages: ["@tremor/react"],
};

export default nextConfig;
