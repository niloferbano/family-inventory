import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  envDir: "..",
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // Lets `npm run dev` also serve a service worker, so you can test the
      // install prompt without doing a full `npm run build` first.
      devOptions: { enabled: true },
      includeAssets: ["favicon-32.png", "apple-touch-icon.png"],
      manifest: {
        name: "Family Inventory",
        short_name: "Inventory",
        description: "Track household inventory and get expiry/low-stock alerts.",
        start_url: "/",
        display: "standalone",
        background_color: "#fbfaf7",
        theme_color: "#1e6b7a",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/maskable-icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // App-shell caching only. Deliberately NOT caching /api/v1/* responses:
        // inventory/notification data changes constantly and is auth-gated, so
        // a stale cached response would be actively misleading. Offline just
        // means "the shell loads but shows a network error," which is the
        // honest state for the freshness this app needs.
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
  server: {
    proxy: {
      "/api/v1": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
    },
  },
});
