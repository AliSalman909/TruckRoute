import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // maplibre-gl (~1.05 MB) ships as one module; deck.gl (~730 kB) is a lazy chunk for the heatmap.
  build: { chunkSizeWarningLimit: 1100 },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
