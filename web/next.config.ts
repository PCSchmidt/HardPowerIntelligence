import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Pin the workspace root to this app — a stray lockfile in a parent directory
  // otherwise causes Next to infer the wrong root.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
