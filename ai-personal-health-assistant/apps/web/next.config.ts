import type { NextConfig } from "next";
import path from "node:path";
const config: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname, "../.."),
  transpilePackages: ["@health/contracts"],
};
export default config;
