import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { execPath } from 'node:process'

const PORT = process.env.PLAYWRIGHT_PORT || '4173'
const baseURL = `http://127.0.0.1:${PORT}`

function run(command, args, options = {}) {
  const child = spawn(command, args, {
    stdio: options.stdio || 'inherit',
    env: {
      ...process.env,
      ...options.env,
    },
  })
  return child
}

async function waitForServer(url, timeoutMs = 30000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(url)
      if (res.ok) return
    } catch {
      // Keep polling until Vite has opened the port.
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error(`Timed out waiting for ${url}`)
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null) return
  child.kill()
  await Promise.race([
    once(child, 'exit'),
    new Promise((resolve) => setTimeout(resolve, 3000)),
  ])
  if (child.exitCode === null) child.kill('SIGKILL')
}

let server
try {
  server = run(execPath, ['./node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', PORT], {
    stdio: 'ignore',
  })
  await waitForServer(baseURL)

  const test = run(execPath, ['./node_modules/@playwright/test/cli.js', 'test'], {
    env: { PLAYWRIGHT_PORT: PORT },
  })
  const [code] = await once(test, 'exit')
  process.exitCode = code || 0
} catch (err) {
  console.error(err instanceof Error ? err.message : err)
  process.exitCode = 1
} finally {
  await stopProcess(server)
}
