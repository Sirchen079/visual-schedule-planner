const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict')
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms))

async function run({mainWindow,getJson,qa,mode}) {
  const js=code=>mainWindow.webContents.executeJavaScript(code,true)
  async function wait(code){for(let i=0;i<180;i++){if(await js(code))return;await delay(100)}throw Error('Event QA timeout: '+code)}
  const click=async selector=>{await js(`document.querySelector(${JSON.stringify(selector)}).click()`);await delay(150)}
  const request=(url,body)=>js(`fetch(${JSON.stringify(url)},{method:'POST',headers:{'Content-Type':'application/json'},body:${JSON.stringify(JSON.stringify(body))}}).then(async r=>{if(!r.ok)throw Error(await r.text());return r.json()})`)
  async function open(id,day){await js(`location.hash=${JSON.stringify(`/calendar?date=${day}&event=${id}`)}`);await wait(`!!document.getElementById('event-reminder-save')&&document.querySelector('[aria-label="事件详情"] .foot').textContent.includes(${JSON.stringify('#'+id)})`)}
  async function save(){await click('#event-reminder-save');await wait(`document.querySelector('[aria-label="事件详情"] [role="status"]')?.textContent.includes('已')`)}
  if(mode==='check') {
    const saved=JSON.parse(fs.readFileSync(path.join(qa,'event-ui.json'),'utf8'))
    assert.deepEqual((await getJson(`/api/schedule/events/${saved.seriesId}`)).remind_offsets,[])
    const allDay=await getJson(`/api/schedule/events/${saved.allDayId}`)
    assert.deepEqual(allDay.remind_offsets,[0]);assert.equal(allDay.reminder_time,'09:00')
    await open(saved.allDayId,'2032-01-16')
    assert.equal(await js(`document.querySelector('[aria-label="全天日程提醒时间"]').value`),'09:00')
    fs.writeFileSync(path.join(qa,'event-restart.json'),JSON.stringify({passed:true,remindersRetained:true}))
    console.log('EVENT_UI_RESTART_PASS');return
  }
  mainWindow.setSize(1450,1000)
  const series=await request('/api/schedule/events',{title:'每周项目会',date:'2032-01-08',start_time:'15:00',end_time:'16:00',recur_rrule:'FREQ=WEEKLY;COUNT=4'})
  await open(series.id,'2032-01-15')
  assert.match(await js(`document.querySelector('[aria-label="事件详情"] .strong').textContent`),/1 月 15 日/)
  await click('[aria-label="事件详情"] input[type="checkbox"][value="30"]');await save()
  assert.deepEqual((await getJson(`/api/schedule/events/${series.id}`)).remind_offsets,[30])
  await js(`(()=>{const e=document.querySelector('[aria-label="事件详情"] input[type="number"]');e.value='90';e.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[aria-label="事件详情"] .custom-reminder button').click()})()`)
  await save();assert.deepEqual((await getJson(`/api/schedule/events/${series.id}`)).remind_offsets,[30,90])
  await js(`document.documentElement.dataset.theme='light'`);await delay(250)
  fs.writeFileSync(path.join(qa,'event-reminders-light.png'),(await mainWindow.webContents.capturePage()).toPNG())
  await js(`document.documentElement.dataset.theme='dark'`);await delay(250)
  fs.writeFileSync(path.join(qa,'event-reminders-dark.png'),(await mainWindow.webContents.capturePage()).toPNG())
  await js(`(()=>{[...document.querySelectorAll('[aria-label="事件详情"] button')].find(b=>b.textContent==='关闭提醒').click()})()`)
  await save();assert.deepEqual((await getJson(`/api/schedule/events/${series.id}`)).remind_offsets,[])
  await click('[aria-label="关闭详情"]')
  const allDay=await request('/api/schedule/events',{title:'全天活动',date:'2032-01-16'})
  await request('/api/schedule/events',{title:'清晨出发',date:'2032-01-16',start_time:'06:00',end_time:'07:00'})
  await open(allDay.id,'2032-01-16');await click('[aria-label="事件详情"] input[type="checkbox"][value="0"]')
  await wait(`document.querySelector('.other-events')?.textContent.includes('清晨出发')&&document.querySelector('.other-events')?.textContent.includes('全天活动')`)
  assert.equal(await js(`document.querySelector('[aria-label="事件详情"] form').checkValidity()`),false)
  await js(`(()=>{const e=document.querySelector('[aria-label="全天日程提醒时间"]');e.value='09:00';e.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await save();assert.equal((await getJson(`/api/schedule/events/${allDay.id}`)).reminder_time,'09:00')
  mainWindow.setSize(990,850);await delay(250)
  assert.equal(await js(`document.documentElement.scrollWidth<=window.innerWidth+2`),true)
  fs.writeFileSync(path.join(qa,'event-reminders-narrow.png'),(await mainWindow.webContents.capturePage()).toPNG())
  await click('[aria-label="关闭详情"]')
  const current=await js(`(()=>{const d=new Date(Date.now()-60000),pad=n=>String(n).padStart(2,'0');return{date:d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()),time:pad(d.getHours())+':'+pad(d.getMinutes())}})()`)
  const due=await request('/api/schedule/events',{title:'原生日程通知验收',date:current.date,start_time:current.time,remind_offsets:[0]})
  let notification
  for(let i=0;i<160;i++){notification=(await getJson('/api/notifications')).find(n=>n.title==='原生日程通知验收');if(notification)break;await delay(250)}
  assert(notification,'Actual scheduler did not deliver event reminder')
  await click('.bell')
  await wait(`!!document.querySelector('a[href="#/calendar?date=${current.date}&event=${due.id}"]')`)
  await click(`a[href="#/calendar?date=${current.date}&event=${due.id}"]`)
  await wait(`!!document.getElementById('event-reminder-save')&&document.querySelector('[aria-label="事件详情"] .title').textContent==='原生日程通知验收'`)
  assert.equal(await js(`location.hash`),`#/calendar?date=${current.date}&event=${due.id}`)
  assert((await getJson('/api/notifications')).find(n=>n.id===notification.id).read_at)
  fs.writeFileSync(path.join(qa,'event-ui.json'),JSON.stringify({passed:true,seriesId:series.id,allDayId:allDay.id,
    checks:['occurrence date shown','advance reminders save','custom minutes save','clear all reminders','explicit all-day clock','real scheduler notification','notification link opens event and marks read','light dark narrow views']}))
  console.log('EVENT_UI_PASS')
}
module.exports={run}
