const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

function load(env = {}, packaged = true) {
  const paths = { appData: 'C:/Users/test/AppData/Roaming', userData: 'unused', exe: 'C:/Programs/app/app.exe' }
  const made = []
  const app = {
    isPackaged: packaged, getPath: key => paths[key], setPath: (key, value) => { paths[key] = value },
    requestSingleInstanceLock: () => false, quit() {}, on() {},
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
    '\nmodule.exports = { resolveDataRoot, backendDir };', context)
  return { ...context.module.exports, paths, made }
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
