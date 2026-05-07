import path from 'path';
import { defineConfig } from 'vite';

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    }
  },
  server: {
    host: '0.0.0.0', // Allow external connections to Vite dev server
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5001', // Point to Flask backend (corrected port)
        changeOrigin: true,
        secure: false,
      }
    }
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  }
});
