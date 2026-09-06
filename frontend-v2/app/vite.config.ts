/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * 开发代理保留浏览器 Host，使其与 Origin 同源，通过后端来源校验。
 * 后端需单独启动并监听 127.0.0.1:8421。
 */
const BACKEND = 'http://127.0.0.1:8421'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: false },
      '/ai': { target: BACKEND, changeOrigin: false },
      '/health': { target: BACKEND, changeOrigin: false },
    },
  },
  build: {
    // 与后端约定的静态托管产物目录（backend-v2 内置 SPA 托管，挂载在 /）。
    // 构建产物由仓库内 backend-v2/frontend/dist 托管。
    outDir: '../../backend-v2/frontend/dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
