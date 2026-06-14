import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true, // WS /api/chat 업그레이드도 백엔드로 중계 (REST 와 동일 계약)
      },
    },
  },
})
