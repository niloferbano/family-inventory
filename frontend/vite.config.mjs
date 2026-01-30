import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/v1": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
    },
    // dev server middleware to rewrite /login -> /login.html
    setup: (server) => {
      // Vite <=4 used `configureServer`; in Vite 5+ (and compatible), `setup` is available.
      // Fallback to `configureServer` if needed by your Vite version.
      server.middlewares.use((req, res, next) => {
        if (req.url === "/login") {
          req.url = "/login.html";
        }
        next();
      });
    },
  },
});