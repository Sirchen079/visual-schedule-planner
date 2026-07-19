import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期：前端 5173，经 proxy 连后端 18731
// 生产期：后端 FastAPI 同时托管前端 + API（单端口 18731）
const backend = 'http://127.0.0.1:18731'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/tasks': backend,
      '/habits': backend,
      '/goals': backend,
      '/journal': backend,
      '/notifications': backend,
      '/stats': backend,
      '/reminders': backend,
      '/settings': backend,
      '/files': backend,
      '/ai': backend,
      '/schedule': backend,
      '/export': backend,
      '/import': backend,
      '/shutdown': backend,
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
