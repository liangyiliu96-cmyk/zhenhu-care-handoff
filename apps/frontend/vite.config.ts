import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiTarget = env.VITE_DEV_API_TARGET || env.VITE_API_BASE || 'http://127.0.0.1:8001';

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/inpatient': { target: apiTarget, changeOrigin: true },
        '/admin/': { target: apiTarget, changeOrigin: true },
        '/ward': { target: apiTarget, changeOrigin: true },
        '/assistant': { target: apiTarget, changeOrigin: true },
        '/nurse/': { target: apiTarget, changeOrigin: true },
        '/monitoring': { target: apiTarget, changeOrigin: true },
        '/patients': { target: apiTarget, changeOrigin: true },
        '/cds-services': { target: apiTarget, changeOrigin: true },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-mui': ['@mui/material', '@mui/icons-material', '@emotion/react', '@emotion/styled'],
            'vendor-charts': ['recharts'],
            'vendor-flow': ['@xyflow/react', '@dagrejs/dagre'],
            'vendor-pdf': ['jspdf', 'html2canvas'],
            'vendor-query': ['@tanstack/react-query'],
          },
        },
      },
    },
  };
});
