import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    port: process.env.PORT ? Number(process.env.PORT) : 5173,
    // Dev: proxy API calls to the FastAPI backend so the browser sees one origin.
    proxy: {
      "/api": { target: "http://127.0.0.1:8099", changeOrigin: true },
    },
  },
})
