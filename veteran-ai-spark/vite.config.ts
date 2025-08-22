import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";
import { visualizer } from "rollup-plugin-visualizer";
import { VitePWA } from "vite-plugin-pwa";

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
    VitePWA({
      registerType: "autoUpdate",
      workbox: { 
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        runtimeCaching: [{
          urlPattern: /^https:\/\/veteransbenefits\.ai\/api\//,
          handler: 'NetworkFirst',
          options: {
            cacheName: 'api-cache',
            expiration: {
              maxEntries: 50,
              maxAgeSeconds: 5 * 60, // 5 minutes
            },
          },
        }],
      },
      manifest: { 
        name: "Veterans Benefits AI",
        short_name: "VetBenefitsAI", 
        description: "AI assistant for U.S. Veterans benefits navigation",
        start_url: "/", 
        display: "standalone",
        background_color: "#0b0b0f",
        theme_color: "#0b0b0f",
        icons: [
          {
            src: "/logo.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any maskable"
          }
        ]
      },
    }),
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
