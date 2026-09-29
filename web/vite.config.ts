import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The pipeline exports to site/public/data (STEPS.md 12b); it ships at /data. SITE_PUBLIC points elsewhere for local checks.
export default defineConfig({
  plugins: [react()],
  base: "./",
  worker: { format: "es" },
  publicDir: process.env.SITE_PUBLIC ?? "../site/public",
});
