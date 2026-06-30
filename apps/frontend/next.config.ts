import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output: a self-contained server bundle (+ minimal node_modules) the Docker image
  // runs with `node server.js`, so the production image stays small.
  output: "standalone",
};

export default nextConfig;
