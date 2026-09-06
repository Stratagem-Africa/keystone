import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The merge gate builds into its OWN directory. `next build` and a running `next dev` otherwise
  // share .next/types/, and tsconfig includes that path — so a concurrent write leaves duplicate
  // generated files ("routes.d 2.ts") and the gate's typecheck fails on code that is fine. A gate
  // that is red 1 run in 3 trains you to ignore red, which is worse than having no gate.
  distDir: process.env.NEXT_DIST_DIR || ".next",
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
