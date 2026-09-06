/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * 后端基址。后端已运行在 http://127.0.0.1:8421（不要在本工程里启停它）。
 *
 * 代理必须 changeOrigin: false，原因（backend-v2/src/zhishi/server/app.py OriginGuardMiddleware）：
 *   1) 请求 Host 的 hostname 必须在回环白名单（127.0.0.1 / localhost / ::1）；
 *   2) 带 Origin 的请求要求 Origin 与 Host 头「同源」，否则 403。
 * 浏览器对同源 fetch 会自动带 Origin: http://localhost:5173；保持 changeOrigin=false
 * 让后端看到的 Host 仍是 localhost:5173，与 Origin 同源，校验通过。
 * （若 changeOrigin=true 把 Host 改写成 127.0.0.1:8421，Origin 与 Host 不再同源 → 403。）
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
    // 相对 app/ 的路径：E:\知时\frontend-v2\app → E:\知时\backend-v2\frontend\dist
    outDir: '../../backend-v2/frontend/dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
