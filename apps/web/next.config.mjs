/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    typedRoutes: true,
  },
  // Transpile Tremor — it ships ESM that Next.js needs to handle
  transpilePackages: ["@tremor/react"],
  async rewrites() {
    // Proxy browser-originated /api/v1/* calls through Next.js to the FastAPI backend.
    // This avoids CORS entirely — the browser only ever talks to its own origin.
    // API_INTERNAL_URL is a server-only secret, never sent to the browser.
    // Local dev: http://localhost:8000  |  Production: Render service URL
    const apiUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
