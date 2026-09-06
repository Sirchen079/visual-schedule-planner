const api = window.zhishiWidget
const $ = id => document.getElementById(id)
let loading = false
let writing = false
function state(s) {
  document.body.classList.toggle('collapsed', s.collapsed)
  $('pin').setAttribute('aria-pressed', String(s.pinned))
  $('pin').title = s.pinned ? '取消置顶' : '置顶'
  $('pin').setAttribute('aria-label', $('pin').title)
  $('collapse').textContent = s.collapsed ? '+' : '−'
  $('collapse').setAttribute('aria-expanded', String(!s.collapsed))
  $('collapse').title = s.collapsed ? '展开' : '收起'
  $('collapse').setAttribute('aria-label', $('collapse').title)
}
function error(e) { $('status').textContent = `未完成，请重试：${e.message || e}` }
function addItem(item, day) {
  const row = document.createElement('div'); row.className = 'item'
  const isTask = item.kind === 'task'
  const control = document.createElement(isTask ? 'button' : 'span')
  control.className = isTask ? 'check' : 'event-dot'
  control.textContent = isTask ? '' : '•'
  if (isTask) {
    control.setAttribute('aria-label', `完成：${item.title}`)
    control.title = '标记完成'
    control.onclick = async () => {
      if (writing) return
      writing = true; control.disabled = true
      try { await api.completeTask(item.task_id); await refresh(); $('status').textContent = '已完成，辛苦了。' }
      catch (e) { error(e); control.disabled = false }
      finally { writing = false }
    }
  }
  const text = document.createElement('div'); text.className = 'item-text'
  const title = document.createElement('div'); title.className = 'item-title'; title.textContent = item.title
  const meta = document.createElement('div'); meta.className = 'meta'
  const overdue = item.due_date && item.due_date.slice(0, 10) < day
  meta.textContent = [overdue ? `逾期 · ${item.due_date.slice(0, 10)}` : item.start_time || item.due_time || '今日待办', item.end_time ? `– ${item.end_time}` : '', item.location || ''].filter(Boolean).join(' ')
  if (overdue) meta.classList.add('overdue')
  text.append(title, meta); row.append(control, text); $('items').append(row)
}
async function refresh() {
  if (loading) return
  loading = true; $('refresh').disabled = true
  try {
    const s = await api.snapshot()
    state(s)
    $('date').textContent = new Date(`${s.day}T12:00:00`).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })
    $('count').textContent = String(s.count)
    $('summary').textContent = s.count ? `今天还有 ${s.count} 项安排` : '今天，留一点从容'
    $('items').replaceChildren()
    for (const i of s.items) addItem(i, s.day)
    for (const t of s.due) addItem({ ...t, kind: 'task', task_id: t.id }, s.day)
    if (!s.count) {
      const empty = document.createElement('p'); empty.className = 'empty'
      empty.textContent = '今天还没有安排。记下一件想做的事，或打开知时一起制定计划。'
      $('items').append(empty)
    }
    $('status').textContent = ''
  } catch (e) { error(e) }
  finally { loading = false; $('refresh').disabled = false }
}
for (const action of ['pin', 'collapse', 'hide', 'main']) {
  $(action).onclick = async () => { try { state(await api.control(action)) } catch (e) { error(e) } }
}
$('refresh').onclick = refresh
$('capture').onsubmit = async e => {
  e.preventDefault()
  if (writing || !$('title').value.trim()) return
  writing = true; $('add').disabled = true
  try {
    await api.createTask($('title').value)
    $('title').value = ''
    await refresh()
    $('status').textContent = '已记入今日待办。'
  } catch (e) { error(e) }
  finally { writing = false; $('add').disabled = false }
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') api.control('hide').catch(error) })
window.addEventListener('focus', refresh)
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh() })
setInterval(() => { if (!document.hidden) refresh() }, 30000)
refresh()
