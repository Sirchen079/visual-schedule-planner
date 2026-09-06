const { app, BrowserWindow } = require('electron')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), assert = require('node:assert/strict')
const qa = path.resolve(process.argv[2]), state = JSON.parse(fs.readFileSync(path.join(qa, 'chat-isolation-state.json'), 'utf8'))
const base = `http://127.0.0.1:${state.port}`
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'zhishi-chat-render-')))
app.disableHardwareAcceleration()
app.on('window-all-closed', () => {}) // The harness opens the widget after closing the main fixture.
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
app.whenReady().then(async () => {
  const errors = []
  let win
  try {
    for (const mode of ['main', 'widget']) {
      win = new BrowserWindow({ width: mode === 'main' ? 1450 : 420, height: 1000, show: false, webPreferences: { offscreen: true, contextIsolation: true, nodeIntegration: false, sandbox: true } })
      win.webContents.on('console-message', (_e, level, message) => { if (level >= 2 && !message.includes('Electron Security Warning')) errors.push(message) })
      const js = code => win.webContents.executeJavaScript(code, true)
      async function wait(code) { for (let i = 0; i < 300; i++) { if (await js(code)) return; await delay(100) } throw Error('Timeout ' + code) }
      async function shot(name) { await delay(300); fs.writeFileSync(path.join(qa, name + '.png'), (await win.webContents.capturePage()).toPNG()) }
      async function send(text) {
        await js(`(()=>{const e=document.querySelector('.chat textarea');e.value=${JSON.stringify(text)};e.dispatchEvent(new Event('input',{bubbles:true}))})()`)
        await wait(`!document.querySelector('.chat .send').disabled && !document.querySelector('.chat .send.stop')`)
        await js(`document.querySelector('.chat .send').click()`)
        await wait(`document.querySelector('.thread-items')?.textContent.includes(${JSON.stringify('已收到 ' + text)}) && !document.querySelector('.chat-head [title="新建会话"]').disabled`)
      }
      async function fresh() {
        await js(`document.querySelector('.chat-head [title="新建会话"]').click()`)
        await wait(`document.querySelector('.chat-head .t')?.textContent==='新对话' && !!document.querySelector('.thread-items .empty')`)
        assert.equal(await js(`document.querySelectorAll('.thread-items .msg-user,.thread-items .msg-ai,.approval-card').length`), 0)
        assert.equal(await js(`document.querySelector('.chat textarea').value`), '')
      }
      await win.loadURL(base + (mode === 'main' ? '/#/' : '/?widget=1#/'))
      await wait(`!!document.querySelector('.chat textarea')`)
      const old = mode === 'main' ? 'CHAT_OLD_ONLY_A' : 'WIDGET_OLD_ONLY_D'
      const first = mode === 'main' ? 'CHAT_NEW_ONLY_B' : 'WIDGET_NEW_ONLY_E'
      await send(old)
      await js(`(()=>{const e=document.querySelector('.chat textarea');e.value='旧会话未发送草稿';e.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('.plan-toggle').click();const files=new DataTransfer();files.items.add(new File(['OLD_DRAFT_ATTACHMENT'],'old-draft.txt',{type:'text/plain'}));const picker=document.querySelector('.chat input[type=file]');picker.files=files.files;picker.dispatchEvent(new Event('change',{bubbles:true}))})()`)
      await wait(`document.querySelector('.chips')?.textContent.includes('old-draft.txt') && !document.querySelector('.chip.uploading')`)
      await fresh()
      assert.equal(await js(`document.querySelector('.plan-toggle').hasAttribute('data-on')`), false)
      assert.equal(await js(`document.querySelectorAll('.chips .chip').length`), 0)
      await shot(`chat-${mode}-new-empty`)
      await send(first)
      assert(!(await js(`document.querySelector('.thread-items').textContent`)).includes(old))
      if (mode === 'main') {
        await send('CHAT_CONTINUE_B')
        assert((await js(`document.querySelector('.thread-items').textContent`)).includes(first))
        await js(`document.querySelector('.chat-head [title="会话列表"]').click()`)
        await wait(`[...document.querySelectorAll('.conv-wrap li')].some(e=>e.textContent.includes('CHAT_OLD_ONLY_A'))`)
        await js(`document.querySelectorAll('.conv-wrap li').forEach(e=>{if(e.textContent.includes('CHAT_OLD_ONLY_A'))e.click()})`)
        await wait(`document.querySelector('.thread-items')?.textContent.includes('已收到 CHAT_OLD_ONLY_A')`)
        assert(!(await js(`document.querySelector('.thread-items').textContent`)).includes('CHAT_NEW_ONLY_B'))
        await js(`document.querySelector('.chat-head [title="会话列表"]').click()`)
        await wait(`!!document.querySelector('.conv-wrap .new')`)
        await js(`document.querySelector('.conv-wrap .new').click()`)
        await wait(`!!document.querySelector('.thread-items .empty')`)
        await send('CHAT_NEW_ONLY_C')
        assert(!(await js(`document.querySelector('.thread-items').textContent`)).includes('CHAT_OLD_ONLY_A'))
      }
      await shot(`chat-${mode}-fresh-reply`)
      win.destroy(); win = null
    }
    assert.deepEqual(errors, [])
    fs.writeFileSync(path.join(qa, 'chat-isolation-ui.json'), JSON.stringify({ passed: true, checks: ['main fresh', 'same-conversation continuation', 'history selection without mixed live output', 'list new button', 'widget fresh', 'draft/plan-mode/attachment clearing'], errors }, null, 2))
    console.log('CHAT_ISOLATION_NATIVE_UI_PASS')
    app.exit(0)
  } catch (error) {
    console.error(error.stack)
    if (win && !win.isDestroyed()) fs.writeFileSync(path.join(qa, 'chat-isolation-failure.png'), (await win.webContents.capturePage()).toPNG())
    fs.writeFileSync(path.join(qa, 'chat-isolation-failure.json'), JSON.stringify({ error: String(error), errors }, null, 2))
    app.exit(1)
  }
})
