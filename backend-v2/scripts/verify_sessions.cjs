const {app,BrowserWindow}=require('electron')
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict')
const qa=path.resolve(process.argv[2]), phase=process.argv[3]
const state=JSON.parse(fs.readFileSync(path.join(qa,'session-state.json'),'utf8')),base=`http://127.0.0.1:${state.port}`
app.setPath('userData',fs.mkdtempSync(path.join(os.tmpdir(),'zhishi-session-render-')))
app.disableHardwareAcceleration()
const sleep=ms=>new Promise(r=>setTimeout(r,ms))
app.whenReady().then(async()=>{
 const windows=[],errors=[],checks=[]
 async function surface(mode){
  const win=new BrowserWindow({width:mode==='main'?1450:420,height:960,show:false,webPreferences:{offscreen:true,contextIsolation:true,nodeIntegration:false,sandbox:true}})
  windows.push(win)
  win.webContents.on('console-message',(_e,level,msg)=>{if(level>=2&&!msg.includes('Electron Security Warning'))errors.push(msg)})
  const js=code=>win.webContents.executeJavaScript(code,true)
  async function wait(code){for(let i=0;i<240;i++){if(await js(code))return;await sleep(100)}throw Error(`Timeout ${mode}: ${code}`)}
  async function input(value){await js(`(()=>{const e=document.querySelector('.chat textarea');e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}))})()`)}
  async function send(value,complete=true){await input(value);await wait(`!!document.querySelector('.chat .send:not(.stop):not([disabled])')`);await js(`document.querySelector('.chat .send').click()`);if(complete)await wait(`document.querySelector('.thread-items')?.textContent.includes(${JSON.stringify('REPLY '+value)})&&!document.querySelector('.chat .send.stop')`)}
  async function select(title){await js(`document.querySelector('.chat-head [title="会话列表"]').click()`);await wait(`[...document.querySelectorAll('.conv-wrap li')].some(e=>e.textContent.includes(${JSON.stringify(title)}))`);await js(`[...document.querySelectorAll('.conv-wrap li')].find(e=>e.textContent.includes(${JSON.stringify(title)})).click()`);await wait(`document.querySelector('.chat-head .t')?.textContent.includes(${JSON.stringify(title)})`)}
  async function shot(label){await sleep(150);fs.writeFileSync(path.join(qa,label+'.png'),(await win.webContents.capturePage()).toPNG())}
  await win.loadURL(base+(mode==='widget'?'/?widget=1#/':'/#/'))
  await wait(`!!document.querySelector('.chat textarea')&&!document.querySelector('.chat textarea').disabled&&!document.querySelector('.context-state')?.textContent.includes('正在加载')`)
  return{win,js,wait,input,send,select,shot}
 }
 try{
  const main=await surface('main'),widget=await surface('widget')
  if(phase==='seed'){
   await main.send('A_SEED');await widget.send('W_SEED')
   await widget.select('A_SEED')
   await main.send('A_SLOW',false)
   await main.wait(`document.querySelector('.thread-items').textContent.includes('PARTIAL_A_SLOW')`)
   await widget.wait(`document.querySelector('.thread-items').textContent.includes('PARTIAL_A_SLOW')`)
   assert((await widget.js(`document.querySelector('.microtext').textContent`)).includes('另一个窗口'))
   await main.js(`document.querySelector('.chat .send.stop').click()`)
   await widget.wait(`document.querySelector('.thread-items').textContent.includes('已中断')`)
   checks.push('same conversation live checkpoint mirrored across windows; cancel persisted')
   await widget.select('W_SEED')
   await main.send('A_AFTER_CANCEL')
   await main.send('APPROVAL_A',false)
   await main.wait(`!!document.querySelector('.approve .btn-no:not([disabled])')`)
   await main.input('MAIN_UNSENT_DRAFT');await widget.input('WIDGET_UNSENT_DRAFT')
   for(let i=0;i<100;i++){
    const a=await fetch(base+'/ai/workspaces/main').then(r=>r.json()),b=await fetch(base+'/ai/workspaces/widget').then(r=>r.json())
    if(a.state.drafts[String(a.state.active_id)]?.text==='MAIN_UNSENT_DRAFT'&&b.state.drafts[String(b.state.active_id)]?.text==='WIDGET_UNSENT_DRAFT'){
     fs.writeFileSync(path.join(qa,'session-selections.json'),JSON.stringify({main:a.state.active_id,widget:b.state.active_id}));break
    }
    if(i===99)throw Error('drafts not persisted');await sleep(100)
   }
   await main.win.reload();await main.wait(`!!document.querySelector('.approve .btn-no:not([disabled])')&&document.querySelector('.chat textarea').value==='MAIN_UNSENT_DRAFT'`)
   checks.push('reload restores current selection, pending approval and unsent draft')
  }else{
   await main.wait(`document.querySelector('.chat textarea').value==='MAIN_UNSENT_DRAFT'&&!!document.querySelector('.approve .btn-no:not([disabled])')`)
   await widget.wait(`document.querySelector('.chat textarea').value==='WIDGET_UNSENT_DRAFT'&&document.querySelector('.chat-head .t').textContent==='W_SEED'`)
   assert(!(await main.js(`document.querySelector('.thread-items').textContent`)).includes('W_SEED'))
   assert(!(await widget.js(`document.querySelector('.thread-items').textContent`)).includes('A_SEED'))
   checks.push('backend port change and fresh renderer profile restore independent main/widget selections and drafts')
   await main.js(`document.querySelector('.approve .btn-no').click()`)
   await main.wait(`document.querySelector('.thread-items').textContent.includes('APPROVAL_RESOLVED')&&!document.querySelector('.chat .send.stop')`)
   assert.equal(await main.js(`document.querySelector('.chat textarea').value`),'MAIN_UNSENT_DRAFT')
   checks.push('recovered approval rejection resumes original conversation without consuming unsent draft')
  }
  await main.shot(`session-${phase}-main`)
  await widget.js(`document.documentElement.setAttribute('data-theme','dark')`)
  await widget.shot(`session-${phase}-widget`)
  assert(await widget.js(`document.documentElement.scrollWidth<=window.innerWidth`))
  assert.deepEqual(errors,[])
  fs.writeFileSync(path.join(qa,`session-ui-${phase}.json`),JSON.stringify({passed:true,checks,errors},null,2))
  windows.forEach(w=>w.destroy());console.log('SESSION_NATIVE_'+phase.toUpperCase()+'_PASS');app.exit(0)
 }catch(e){
  console.error(e.stack)
  for(let i=0;i<windows.length;i++)if(!windows[i].isDestroyed())fs.writeFileSync(path.join(qa,`session-${phase}-failure-${i}.png`),(await windows[i].webContents.capturePage()).toPNG())
  fs.writeFileSync(path.join(qa,`session-ui-${phase}-failure.json`),JSON.stringify({error:String(e),errors},null,2));app.exit(1)
 }
})
