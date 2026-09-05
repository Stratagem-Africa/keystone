import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Cloudflare Workers — disables Node.js-specific image optimisation.
  images: { unoptimized: true },
  // The dev indicator's default bottom-left position sits directly on top of the studio's
  // load-transport button, covering a primary control while you work. Every other corner of the
  // studio is occupied too — design card top-left, Map/Edit top-right, zoom cluster at the
  // canvas's bottom-right — but the viewport's bottom-right falls inside the (scrollable) rail
  // rather than on a control, so that is the least-bad home for it.
  devIndicators: { position: "bottom-right" },
};

export default nextConfig;
