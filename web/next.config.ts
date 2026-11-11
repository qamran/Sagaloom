import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The Playwright demo's web server sets NEXT_DIST_DIR=.next-e2e, so it can run next to `pnpm dev`
  // (Next locks its build folder to one dev server). Unset, it is Next's default.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
