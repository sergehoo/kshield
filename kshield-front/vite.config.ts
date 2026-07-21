import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      host: true,
      // Proxy /api → backend Django en dev (évite les CORS)
      proxy: {
        "/api": {
          target: env.VITE_API_TARGET || "https://api.kaydanshield.com",
          changeOrigin: true,
          secure: true,
        },
      },
    },
    preview: {
      port: 4173,
      host: true,
    },
    build: {
      outDir: "dist",
      sourcemap: false,
      target: "es2020",
      rollupOptions: {
        output: {
          manualChunks: {
            react: ["react", "react-dom", "react-router-dom"],
            query: ["@tanstack/react-query", "axios", "zustand"],
            charts: ["recharts"],
            maps: ["leaflet"],
            icons: ["lucide-react"],
          },
        },
      },
    },
  };
});
