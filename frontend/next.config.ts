import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Cloudflare Workers — disables Node.js-specific image optimisation.
  images: { unoptimized: true },
};

export default nextConfig;
