import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  ...(process.env.NEXT_OUTPUT_MODE === "export" ? { output: "export" } : {}),
  // Keep output-file tracing scoped to the frontend app so build traces do not
  // walk reference-only sibling folders under external/.
  experimental: {
    outputFileTracingRoot: frontendRoot,
  },
};

export default nextConfig;

