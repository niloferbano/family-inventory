import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const restAPI = "http://127.0.0.1:8000";
export default defineConfig({
  envDir: "..",
  plugins: [react()],
  server: {
    proxy: {
      "/api/v1": {
        target: restAPI,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
