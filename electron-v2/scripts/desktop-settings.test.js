const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { createDesktopSettings } = require('../desktop-settings')

function setup(stateDir) {
  const handlers = new Map(), sent = [], listeners = new Set()
  const state = {visible:true,pinned:true,collapsed:false,shortcutRegistered:false}
  const widget = { preferences: () => ({...state}), setPreferences(patch) {Object.assign(state,patch);for(const fn of listeners)fn()},
    onChange(fn) {listeners.add(fn);return()=>listeners.delete(fn)} }
  const frame = {url:'http://127.0.0.1:8421/#/settings'}
  const win = {isDestroyed:()=>false,webContents:{mainFrame:frame,send:(...args)=>sent.push(args)}}
  const event = {sender:win.webContents,senderFrame:frame}
  const api = createDesktopSettings({ipcMain:{handle:(k,fn)=>handlers.set(k,fn),removeHandler:k=>handlers.delete(k)},
    getMainWindow:()=>win,widget,baseUrl:'http://127.0.0.1:8421',stateDir})
  return {handlers,sent,state,event,api,listeners}
}

test('desktop preferences bind to the main frame and survive restart', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(),'zhishi-desktop-prefs-'))
  const t = setup(dir), read=t.handlers.get('desktop:preferences'), write=t.handlers.get('desktop:update-preferences')
  assert.equal(read(t.event).notifications,true)
  assert.throws(()=>read({sender:{},senderFrame:t.event.senderFrame}),/不允许/)
  assert.throws(()=>read({...t.event,senderFrame:{url:t.event.senderFrame.url}}),/不允许/)
  for(const url of ['https://example.org/','http://127.0.0.1:8421/?widget=1','http://127.0.0.1:8421/foreign']) {
    t.event.senderFrame.url=url;assert.throws(()=>read(t.event),/不允许/)
  }
  t.event.senderFrame.url='http://127.0.0.1:8421/#/settings'
  for(const patch of [null,[],{visible:'false'},{visible:false,pinned:false},{unknown:true}]) assert.throws(()=>write(t.event,patch),/设置/)
  assert.equal(write(t.event,{visible:false}).visible,false)
  assert.equal(write(t.event,{notifications:false}).notifications,false)
  assert(t.sent.some(([name,state])=>name==='desktop:preferences-changed'&&!state.visible))
  t.api.dispose();assert.equal(t.handlers.size,0);assert.equal(t.listeners.size,0)
  const next=setup(dir);assert.equal(next.api.snapshot().notifications,false);next.api.dispose()
})

test('failed preference write is reported without changing active notification state', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(),'zhishi-desktop-failure-'))
  fs.mkdirSync(path.join(dir,'desktop.json'))
  const t=setup(dir)
  assert.throws(()=>t.handlers.get('desktop:update-preferences')(t.event,{notifications:false}))
  assert.equal(t.api.snapshot().notifications,true)
  t.api.dispose()
})
