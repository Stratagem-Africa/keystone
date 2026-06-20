import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Cloudflare Workers — disables Node.js-specific image optimisation.
  images: { unoptimized: true },
  // Allows the Windows browser to reach the dev server running inside WSL2.
  allowedDevOrigins: ["172.25.106.249"],
};

export default nextConfig;
