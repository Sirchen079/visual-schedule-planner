// 深链白名单单测：main.js 的 internalDeepLink 决定通知 target_path 能否注入
// location.hash（/chat?conversation=N 为 AI 运行通知新增形态）。
// 采用与 main.test.js 相同的 vm 加载方式：mock electron/fs 后导出内部函数。
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

function loadMain() {
  const paths = { appData: 'C:/Users/test/AppData/Roaming', userData: 'unused' }
  const app = {
    isPackaged: true, getPath: (key) => paths[key], setPath: (key, value) => { paths[key] = value },
    requestSingleInstanceLock: () => false, quit() {}, on() {},
  }
  const context = {
    require(name) {
      if (name === 'electron') return { app }
      if (name === 'fs') return { mkdirSync: () => {} }
      return require(name)
    },
    process: { env: {}, argv: [], resourcesPath: 'C:/Programs/app/resources' },
    __dirname: 'E:/repo/electron-v2', console, setTimeout, clearTimeout, setInterval, clearInterval,
    module: { exports: {} },
  }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8') +
    '\nmodule.exports = { internalDeepLink };', context)
  return context.module.exports
}

test('chat conversation deep link is whitelisted', () => {
  const { internalDeepLink } = loadMain()
  assert.equal(internalDeepLink('/chat?conversation=1'), true)
  assert.equal(internalDeepLink('/chat?conversation=42'), true)
})

test('malformed chat targets are rejected', () => {
  const { internalDeepLink } = loadMain()
  for (const bad of ['/chat?conversation=0', '/chat?conversation=-3', '/chat?conversation=1.5',
    '/chat?conversation=12&extra=1', '/chat', '/chat?conversation=abc',
    '/chat?conversation=12 OR 1=1', '//chat?conversation=12', '']) {
    assert.equal(internalDeepLink(bad), false, JSON.stringify(bad))
  }
})

test('existing deep link forms stay whitelisted', () => {
  const { internalDeepLink } = loadMain()
  assert.equal(internalDeepLink('/board?task=9'), true)
  assert.equal(internalDeepLink('/ledger?bill=3'), true)
  assert.equal(internalDeepLink('/calendar?date=2026-09-23&event=5'), true)
  assert.equal(internalDeepLink('/research?project=2'), true)
  assert.equal(internalDeepLink('/research?project=2&followup=7'), true)
})

test('arbitrary internal paths stay rejected', () => {
  const { internalDeepLink } = loadMain()
  assert.equal(internalDeepLink('/settings?section=desktop'), false)
  assert.equal(internalDeepLink('/board?task=9&x=1'), false)
  assert.equal(internalDeepLink('/calendar?date=2026-09-23&event=5&x=1'), false)
})
