import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";
import { visualizer } from "rollup-plugin-visualizer";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
  },
  plugins: [
    react(),
    mode === 'development' &&
    componentTagger(),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    target: "es2018",
    minify: "esbuild",
    cssCodeSplit: true,
    assetsInlineLimit: 0,
    sourcemap: false,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      plugins: [
        visualizer({ 
          filename: "dist/stats.html", 
          gzipSize: true, 
          brotliSize: true,
          open: false
        })
      ],
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("recharts") || id.includes("d3-")) return "vendor-charts";
            if (id.includes("react-simple-maps")) return "vendor-maps";
            if (id.includes("@radix-ui") || id.includes("@hookform")) return "vendor-ui";
            if (id.includes("react-router")) return "vendor-router";
            return "vendor";
          }
        },
      },
    },
  },
}));
