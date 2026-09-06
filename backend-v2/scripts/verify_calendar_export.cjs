const {app,BrowserWindow}=require('electron')
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict')
const qa=path.resolve(process.argv[2]),state=JSON.parse(fs.readFileSync(path.join(qa,'export-state.json'),'utf8'))
const base=`http://127.0.0.1:${state.port}`,sleep=ms=>new Promise(r=>setTimeout(r,ms))
app.setPath('userData',fs.mkdtempSync(path.join(os.tmpdir(),'zhishi-export-render-')))
app.disableHardwareAcceleration()
app.whenReady().then(async()=>{
 const win=new BrowserWindow({width:1450,height:960,show:false,webPreferences:{offscreen:true,contextIsolation:true,nodeIntegration:false,sandbox:true}})
 const js=code=>win.webContents.executeJavaScript(code,true)
 let blocked=true,downloadState=null,downloadName=null
 win.webContents.session.webRequest.onBeforeRequest({urls:[base+'/api/ical/export']},(_d,cb)=>cb({cancel:blocked}))
 win.webContents.session.on('will-download',(_e,item)=>{
  downloadName=item.getFilename();item.setSavePath(path.join(qa,'downloaded-calendar.ics'))
  item.once('done',(_e,state)=>{downloadState=state})
 })
 async function wait(code){for(let i=0;i<150;i++){if(await js(code))return;await sleep(100)}throw Error('Timeout '+code)}
 async function shot(name){fs.writeFileSync(path.join(qa,name+'.png'),(await win.webContents.capturePage()).toPNG())}
 try{
  await win.loadURL(base+'/#/calendar')
  await wait(`!!document.querySelector('#calendar-export')`)
  await js(`document.querySelector('#calendar-export').click()`)
  await wait(`!!document.querySelector('.export-status[role="alert"]')&&!document.querySelector('#calendar-export').disabled`)
  assert.equal(downloadState,null)
  blocked=false;await js(`document.querySelector('.export-status button').click()`)
  await wait(`!!document.querySelector('.export-status[role="status"]')`)
  for(let i=0;i<100&&downloadState===null;i++)await sleep(100)
  assert.equal(downloadState,'completed');assert.match(downloadName,/\.ics$/)
  assert((await js(`document.querySelector('.export-status').textContent`)).includes('后续修改需重新导出'))
  await shot('export-wide');win.setSize(900,900);await sleep(250)
  assert(await js(`(()=>{const r=document.querySelector('#calendar-export').getBoundingClientRect();return r.width>0&&r.left>=0&&r.right<=innerWidth&&r.bottom<innerHeight})()`))
  await shot('export-narrow')
  fs.writeFileSync(path.join(qa,'export-ui.json'),JSON.stringify({passed:true,downloadState,downloadName},null,2))
  win.destroy();app.exit(0)
 }catch(e){console.error(e.stack);await shot('export-failure');app.exit(1)}
})
