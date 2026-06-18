import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期：前端 5173，经 proxy 连后端 8000
// 生产期：后端 FastAPI 同时托管前端 + API（单端口 8000）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/tasks': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
