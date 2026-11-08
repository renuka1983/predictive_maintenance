import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const target = process.env.VITE_BACKEND ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target, changeOrigin: true },
      '/ws': { target: target.replace(/^http/, 'ws'), ws: true },
    },
  },
  build: { chunkSizeWarningLimit: 2500 },
});
