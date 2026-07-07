#!/usr/bin/env node
/**
 * 打包编排：构建前端 → PyInstaller 打包后端 → 复制产物到 desktop/build/backend-dist/
 *
 * 用法：在 desktop/ 下执行 `node scripts/build-backend.js`
 * 前置：项目根有 frontend/（含 package.json）与 backend/（含 .venv 与 zhishi-backend.spec）
 */
const { execSync } = require('child_process')
const path = require('path')
const fs = require('fs')

const ROOT = path.resolve(__dirname, '..', '..')
const FRONTEND = path.join(ROOT, 'frontend')
const BACKEND = path.join(ROOT, 'backend')
const VENV_PY = path.join(BACKEND, '.venv', 'Scripts', 'python.exe')
const DIST_TARGET = path.join(__dirname, '..', 'build', 'backend-dist')

function run(cmd, opts = {}) {
  console.log(`> ${cmd}`)
  execSync(cmd, {
    stdio: 'inherit',
    shell: process.platform === 'win32' ? 'cmd.exe' : true,
    ...opts,
  })
}

function step(name, fn) {
  console.log(`\n=== ${name} ===`)
  fn()
}

step('1. 构建前端 (npm install + npm run build)', () => {
  run('npm install', { cwd: FRONTEND })
  run('npm run build', { cwd: FRONTEND })
})

step('2. PyInstaller 打包后端', () => {
  if (!fs.existsSync(VENV_PY)) {
    throw new Error(`未找到 venv: ${VENV_PY}\n请先执行：python -m venv backend\\.venv && backend\\.venv\\Scripts\\python.exe -m pip install -r backend\\requirements.txt pyinstaller`)
  }
  run(`"${VENV_PY}" -m PyInstaller zhishi-backend.spec --noconfirm`, { cwd: BACKEND })
})

step('3. 复制后端产物到 desktop/build/backend-dist/', () => {
  const src = path.join(BACKEND, 'dist', 'zhishi-backend')
  if (!fs.existsSync(src)) throw new Error(`PyInstaller 产物不存在: ${src}`)
  const dest = path.join(DIST_TARGET, 'zhishi-backend')
  fs.rmSync(DIST_TARGET, { recursive: true, force: true })
  fs.mkdirSync(DIST_TARGET, { recursive: true })
  // 注意：node fs.cpSync 在中文路径 + 大目录下会触发段错误，改用 robocopy
  // robocopy 返回码 0–7 均为成功，>=8 才是错误
  try {
    execSync(`robocopy "${src}" "${dest}" /E /NFL /NDL /NJH /NJS`, {
      stdio: 'ignore',
      shell: 'cmd.exe',
    })
  } catch (e) {
    if (e.status == null || e.status >= 8) throw e
  }
  console.log(`已复制 → ${dest}`)
})

console.log('\n后端打包完成。下一步：cd desktop && npm install && npm run dist')
