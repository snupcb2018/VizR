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
    port: 5174,  // 개발용 포트
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5002', // 개발용 백엔드 포트
        changeOrigin: true,
        secure: false,
      },
      '/socket.io': {
        target: 'http://127.0.0.1:5002', // WebSocket 프록시
        changeOrigin: true,
        ws: true,
      }
    }
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  }
});
