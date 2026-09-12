const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { EventEmitter } = require('node:events')

function load(env = {}, packaged = true) {
  const paths = { appData: 'C:/Users/test/AppData/Roaming', userData: 'unused', exe: 'C:/Programs/app/app.exe' }
  const made = [], events = new Map()
  const app = {
    isPackaged: packaged, getPath: key => paths[key], setPath: (key, value) => { paths[key] = value },
    requestSingleInstanceLock: () => false, quit() {}, on(name, callback) { events.set(name, callback) },
  }
  const context = {
    require(name) {
      if (name === 'electron') return { app }
      if (name === 'fs') return { mkdirSync: p => made.push(p) }
      return require(name)
    },
    process: { env, argv: [], resourcesPath: 'C:/Programs/app/resources' },
    __dirname: 'E:/repo/electron-v2', console, setTimeout, clearTimeout, setInterval, clearInterval,
    module: { exports: {} },
  }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8') +
    '\nmodule.exports = { resolveDataRoot, backendDir, shutdownAndQuit, setBackendForTest(child, request) { backend = child; backendPort = 1234; postShutdown = request } };', context)
  return { ...context.module.exports, paths, made, events }
}

test('installed data stays outside installation directory', () => {
  const shell = load()
  assert.equal(shell.paths.userData, path.join('C:/Users/test/AppData/Roaming', 'ZhishiV2'))
  assert.equal(shell.resolveDataRoot(), path.join(shell.paths.userData, 'data'))
  assert.ok(!shell.resolveDataRoot().startsWith('C:/Programs'))
})

test('explicit isolated userData also isolates packaged database', () => {
  const shell = load({ ZHISHI_SHELL_USER_DATA_DIR: 'C:/Temp/release-check/user' })
  assert.equal(shell.resolveDataRoot(), path.join('C:/Temp/release-check/user', 'data'))
})

test('explicit data root wins without touching old production directories', () => {
  const shell = load({ ZHISHI_SHELL_DATA_DIR: 'C:/Temp/release-check/data' })
  assert.equal(shell.resolveDataRoot(), 'C:/Temp/release-check/data')
  assert.deepEqual(shell.made, [path.join('C:/Temp/release-check/data', 'v2')])
})

test('development data stays in the development workspace', () => {
  assert.equal(load({}, false).resolveDataRoot(), path.join('E:/repo/electron-v2', 'dev-data'))
})

test('concurrent shutdown callers wait for the same backend exit', async () => {
  const shell = load(), child = new EventEmitter()
  child.exitCode = null; child.signalCode = null
  child.kill = () => { throw new Error('Unexpected forced shutdown') }
  let finishRequest
  shell.setBackendForTest(child, () => new Promise(resolve => { finishRequest = resolve }))
  const first = shell.shutdownAndQuit({ quit: false })
  let secondFinished = false
  const second = shell.shutdownAndQuit({ quit: false }).then(() => { secondFinished = true })
  await new Promise(resolve => setImmediate(resolve))
  const finishedTooSoon = secondFinished
  finishRequest()
  await new Promise(resolve => setImmediate(resolve))
  child.exitCode = 0; child.emit('exit', 0)
  await Promise.all([first, second])
  assert.equal(finishedTooSoon, false, 'install must not proceed while another caller is still shutting down')
})

test('forced shutdown waits for actual exit after kill', async () => {
  const shell = load(), child = new EventEmitter()
  child.exitCode = null; child.signalCode = null
  let actuallyExited = false
  child.kill = () => {
    setTimeout(() => { actuallyExited = true; child.signalCode = 'SIGTERM'; child.emit('exit', null, 'SIGTERM') }, 50)
    return true
  }
  shell.setBackendForTest(child, async () => {})
  await shell.shutdownAndQuit({ quit: false })
  assert.equal(actuallyExited, true, 'kill only requests termination; installer must wait for exit')
})

test('shutdown rejects if the backend still remains after kill', async () => {
  const shell = load(), child = new EventEmitter()
  child.exitCode = null; child.signalCode = null; child.kill = () => false
  shell.setBackendForTest(child, async () => {})
  await assert.rejects(shell.shutdownAndQuit({ quit: false }), /后端进程尚未退出/)
  assert.equal(child.listenerCount('exit'), 0)
  child.exitCode = 0
  await shell.shutdownAndQuit({ quit: false })
})


test('a second before-quit cannot bypass an unfinished backend shutdown', async () => {
  const shell = load(), child = new EventEmitter()
  child.exitCode = null; child.signalCode = null
  let finishRequest
  shell.setBackendForTest(child, () => new Promise(resolve => { finishRequest = resolve }))
  const stopping = shell.shutdownAndQuit({ quit: false })
  let prevented = false
  shell.events.get('before-quit')({ preventDefault() { prevented = true } })
  finishRequest()
  child.exitCode = 0; child.emit('exit', 0)
  await stopping
  assert.equal(prevented, true)
})
