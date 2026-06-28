import { existsSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const distDir = resolve(__dirname, '../dist')

rmSync(distDir, { recursive: true, force: true })

if (existsSync(distDir) && process.platform === 'win32') {
  const result = spawnSync(
    'powershell.exe',
    [
      '-NoProfile',
      '-Command',
      "if (Test-Path -LiteralPath $env:DIST_DIR) { Remove-Item -LiteralPath $env:DIST_DIR -Recurse -Force }",
    ],
    {
      env: { ...process.env, DIST_DIR: distDir },
      stdio: 'inherit',
    }
  )
  if (result.status !== 0) process.exit(result.status || 1)
}

if (existsSync(distDir)) {
  throw new Error(`Unable to remove ${distDir}`)
}
