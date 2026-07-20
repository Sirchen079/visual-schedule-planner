// 暖心个性化提醒：根据当前时间、任务安排与真实活跃时长，生成温和的中文提示。
// 纯前端派生：任务数据来自看板 props；活跃信号源有两条，按可用性自动择优：
//   1. Electron 系统级空闲时间（powerMonitor.getSystemIdleTime）——桌面应用首选，
//      用户在任意窗口（IDE/浏览器/Excel…）操作都算活跃，知时在后台也能感知；
//   2. web 交互事件（鼠标 / 键盘 / 滚动 / 触摸）——开发模式浏览器直连时回退。
// 空闲超过 IDLE_THRESHOLD_MS 即视为中断——避免「电脑一直开着就被当作一直在工作」，
// 同时也避免「用户在别的窗口认真工作却被误判为离开」。
// 每分钟重新评估一次，无需后端配合。
// 文案采用多句池 + 按天轮换（种子=当天）：同一天内内容稳定不跳动，第二天自动换一批说法。
import { computed, ref } from 'vue'

const now = ref(Date.now())
setInterval(() => (now.value = Date.now()), 60_000)
// 窗口从后台恢复或重新获焦时立即刷新时钟：覆盖电脑睡眠唤醒、最小化到托盘等
// 场景——setInterval 在后台被节流且不补发错过的回调，隔夜恢复后若仅靠 60s
// 轮询，暖心提示会延迟最多一分钟才对齐当前时段。
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) now.value = Date.now()
  })
}
if (typeof window !== 'undefined') {
  window.addEventListener('focus', () => (now.value = Date.now()))
}

// ---- 真实活跃时长：监听用户交互，空闲超阈值则中断当前连续工作段 ----
const IDLE_THRESHOLD_MS = 5 * 60_000 // 5 分钟内无任何交互，视为「人已离开」
const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'wheel', 'touchstart']
const SESSION_KEY = 'zhishi_session_start'

// 模块级单例：多个组件实例共用同一份活跃状态，避免重复绑定监听器
let lastActiveAt = Date.now()
let streakStartAt = Date.now()
let lastMark = 0
let listenersBound = false

function markActive() {
  const t = Date.now()
  // 节流：1 秒内只处理一次（mousemove 高频），降低无谓的计算
  if (t - lastMark < 1000) return
  lastMark = t
  // 离开过一段时间：当前连续工作段到此为止，下次活动重新起算
  if (t - lastActiveAt > IDLE_THRESHOLD_MS) {
    streakStartAt = t
  }
  lastActiveAt = t
}

function bindActivityOnce() {
  if (listenersBound || typeof window === 'undefined') return
  listenersBound = true
  for (const evt of ACTIVITY_EVENTS) {
    // 仅用于感知活跃，不拦截：passive
    window.addEventListener(evt, markActive, { passive: true })
  }
}
bindActivityOnce()

// Electron 系统级空闲检测：桌面环境下每 15 秒问一次系统空闲秒数，
// 空闲 < 阈值即视为仍在活跃（覆盖「知时挂在后台、用户在别的窗口工作」的场景）。
// 非桌面环境（浏览器开发模式）无 electronAPI，自动跳过，回退到上面的 web 事件检测。
async function pollSystemIdle() {
  const api = typeof window !== 'undefined' ? window.electronAPI : null
  if (!api || typeof api.getSystemIdleTime !== 'function') return
  try {
    const idleSec = await api.getSystemIdleTime()
    if (idleSec * 1000 < IDLE_THRESHOLD_MS) markActive()
  } catch {
    // IPC 不可用：静默回退到 web 事件检测
  }
}
let idlePollBound = false
function bindIdlePollOnce() {
  if (idlePollBound || typeof window === 'undefined') return
  idlePollBound = true
  setInterval(pollSystemIdle, 15_000)
}
bindIdlePollOnce()

function sessionStart() {
  let ts = Number(sessionStorage.getItem(SESSION_KEY))
  // 没有记录或记录异常（未来/超过 12 小时前）时重置为现在
  if (!ts || ts > Date.now() || Date.now() - ts > 12 * 3600_000) {
    ts = Date.now()
    sessionStorage.setItem(SESSION_KEY, String(ts))
  }
  return ts
}

/**
 * 当前「连续工作段」的时长（ms）。
 * 只有用户最近 IDLE_THRESHOLD_MS 内仍在交互时才返回非零；
 * 离开后再回来，会从重新活动的那一刻起算——电脑空转不再被计入。
 */
function activeStreakMs(t = Date.now()) {
  if (t - lastActiveAt > IDLE_THRESHOLD_MS) return 0
  return Math.max(0, t - streakStartAt)
}

function dayRange(offsetDays = 0) {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  start.setDate(start.getDate() + offsetDays)
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  return [start, end]
}

function fmtDuration(ms) {
  const min = Math.floor(ms / 60_000)
  if (min < 60) return `${min} 分钟`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m ? `${h} 小时 ${m} 分` : `${h} 小时`
}

const pick = (arr, seed) => arr[seed % arr.length]

// ---- 文案池：以意象与留白为骨，保留温度而不堆砌辞藻 ----

// 深夜（23:00–05:00）：主线只谈休息，不制造焦虑
const LATE_NIGHT = [
  '夜已深。屏幕的光再亮，也照不亮明天的疲惫——去睡吧。',
  '万籁俱寂之时，最该放下的，是手里那件没做完的事。',
  '熬夜换来的进度，常常抵不过一个好觉换来的清醒。',
]
const LATE_NIGHT_DONE = (n) => [
  `今日已了结 ${n} 件事。把这份心安，一并带进梦里。`,
  `${n} 件事尘埃落定。今夜，可以踏实合眼了。`,
]
const LATE_NIGHT_TODO = [
  '未尽之事，且交给明天的自己——他常比你想象中更能干。',
  '把没做完的写在纸上，然后关灯。明天自有明天的力气。',
]

// 时段暖心句
const TIME_SLOTS = [
  {
    from: 5, to: 9, title: '早上好', icon: 'sun', tone: 'sand',
    lines: [
      '晨光初破，万物方醒。趁头脑清明，先动手做最难的那件事。',
      '一日之计在于晨。深吸一口新空气，想清楚今天最值得的三件事。',
      '清晨的专注最珍贵——别让它碎在第一条消息里。',
    ],
  },
  {
    from: 9, to: 11, title: '上午好', icon: 'sun', tone: 'aqua',
    lines: [
      '日上三竿，正是出活的好时辰。把最硬的骨头挑出来，趁热打铁。',
      '精力正盛。挑一件最动脑的事，沉进去——一小时的深专注，胜过半日的浅忙碌。',
      '上午的时光如未落墨的宣纸，先落最重要那一笔。',
    ],
  },
  {
    from: 11, to: 13, title: '中午好', icon: 'sun', tone: 'sand',
    lines: [
      '忙了一上午，该把笔搁下了。好好吃顿饭，是对下午最划算的投资。',
      '正午已至。先放下手头的事——饭菜要趁热，事可以慢慢来。',
      '饭后小憩十五分钟，下午的清明，会还你一份惊喜。',
    ],
  },
  {
    from: 13, to: 18, title: '下午好', icon: 'sun', tone: 'aqua',
    lines: [
      '午后易倦。泡杯茶，起身走走——慢一点，反而走得更远。',
      '日影西斜，离收工渐近。看看今天，还能顺手了结哪一桩。',
      '困意上涌时，活动活动肩颈。身体松一分，思路便清一分。',
    ],
  },
  {
    from: 18, to: 23, title: '晚上好', icon: 'moon', tone: 'aqua',
    lines: [
      '辛苦了一天。夜里的时间，记得留一些给自己——给喜欢的人，给喜欢的书。',
      '华灯初上。今日尽力便好，余下的，且交给明天。',
      '晚饭要好好吃，晚风要慢慢吹。这一刻，不属于任何任务。',
    ],
  },
]

// 任务情境句（函数接收数量 n）
const MSG_OVERDUE = (n) => [
  `有 ${n} 件事已逾期。别自责——挑最小的那一件，从现在起，重新出发。`,
  `${n} 件事过了期。没关系，今天能动手，就不算太晚。`,
  `逾期的 ${n} 件事在等你。先解开拖得最久的那一个，心里会轻一大截。`,
]
const MSG_DUE_TODAY = (n) => [
  `今天有 ${n} 件事到期。把它们放在前面，其余的，暂且搁置。`,
  `${n} 件事今日截止。一件一件来，急不得。`,
  `今日 ${n} 个截止——做完它们，今晚会格外踏实。`,
]
const MSG_DUE_TOMORROW = (n) => [
  `明天有 ${n} 件事到期。今天先起个头，明天就轻松许多。`,
  `${n} 件事明天截止——今日埋下伏笔，明日水到渠成。`,
]
const MSG_EMPTY = [
  '新的一天，从第一件事开始。把脑海里盘旋的念头，先写下来。',
  '看板尚空。落下一笔，心便有了着落。',
]
const MSG_ALL_CLEAR = [
  '手头暂无挂碍。这难得的空档，可以整理，也可以纯粹地歇一歇。',
  '任务清零。这份清爽，是你一寸一寸挣来的。',
]
const MSG_DOING = (n) => [
  `有 ${n} 件事正在路上。不徐不疾，稳稳推进，便已是好的节奏。`,
  `${n} 件事进行中——慢一点没关系，关键是别停下。`,
]
const MSG_DEFAULT = [
  '一切都已就绪。挑一件最重要的，从五分钟开始。',
  '万事俱备。现在，从最重要的那一件，落下第一笔。',
]

// 完成肯定 / 休息提醒
const MSG_PRAISE = (n) => [
  `今天已完成 ${n} 件事。这份踏实的进展，值得为自己记上一笔。`,
  `今天搞定 ${n} 件了。给自己一个会心的眼神——你做到了。`,
]
const MSG_BREAK_LONG = (d) => [
  `已专注 ${d} 了。认真固然可贵，歇息亦是效率的一部分——起来走走，五分钟便好。`,
  `专注 ${d} 了，身体在悄悄提醒你。倒杯水，看看窗外，让眼睛也歇一歇。`,
]
const MSG_BREAK_SHORT = (d) => [
  `已专注 ${d}。眨眨眼，眺望远处，让目光松一松。`,
  `专注 ${d} 了，伸个懒腰，再继续也不迟。`,
]

/**
 * @param {() => Array} getTasks 返回当前任务数组的 getter（通常是 () => props.tasks）
 * @returns {{ warm: import('vue').ComputedRef<{title:string,icon:string,tone:string,lines:string[]}> }}
 */
export function useWarmGreeting(getTasks) {
  const warm = computed(() => {
    const t = now.value // 依赖分钟级时钟，驱动重算
    const hour = new Date(t).getHours()
    // 轮换种子=当天（UTC 天数），同一天内文案稳定、跨天换说法
    const seed = Math.floor(t / 86_400_000)
    const tasks = getTasks() || []

    const [todayStart, todayEnd] = dayRange(0)
    const [, tomorrowEnd] = dayRange(1)

    const active = tasks.filter((x) => x.status !== '完成' && !x.deleted_at)
    const withDue = active.filter((x) => x.due_date)
    const overdue = withDue.filter((x) => new Date(x.due_date) < todayStart)
    const dueToday = withDue.filter((x) => {
      const d = new Date(x.due_date)
      return d >= todayStart && d < todayEnd
    })
    const dueTomorrow = withDue.filter((x) => {
      const d = new Date(x.due_date)
      return d >= todayEnd && d < tomorrowEnd
    })
    const doing = active.filter((x) => x.status === '进行中')
    const doneToday = tasks.filter(
      (x) => x.status === '完成' && x.updated_at && new Date(x.updated_at) >= todayStart
    )

    // 深夜：休息优先
    if (hour >= 23 || hour < 5) {
      const lines = [pick(LATE_NIGHT, seed)]
      if (doneToday.length) lines.push(pick(LATE_NIGHT_DONE(doneToday.length), seed))
      else lines.push(pick(LATE_NIGHT_TODO, seed))
      return { title: '夜深了', icon: 'moon', tone: 'aqua', mood: 'late', lines }
    }

    const slot = TIME_SLOTS.find((s) => hour >= s.from && hour < s.to) || TIME_SLOTS[0]
    // mood 驱动卡片色调：白天=暖阳、夜晚=静谧蓝、深夜=沉静
    const mood = hour >= 18 ? 'night' : 'day'
    const lines = []

    // 主线：按任务紧迫程度取一条
    if (overdue.length) lines.push(pick(MSG_OVERDUE(overdue.length), seed))
    else if (dueToday.length) lines.push(pick(MSG_DUE_TODAY(dueToday.length), seed))
    else if (dueTomorrow.length) lines.push(pick(MSG_DUE_TOMORROW(dueTomorrow.length), seed))
    else if (!tasks.length) lines.push(pick(MSG_EMPTY, seed))
    else if (!active.length) lines.push(pick(MSG_ALL_CLEAR, seed))
    else if (doing.length) lines.push(pick(MSG_DOING(doing.length), seed))
    else lines.push(pick(MSG_DEFAULT, seed))

    // 时段暖心句
    lines.push(pick(slot.lines, seed))

    // 副线：休息提醒——基于真实活跃段，离开过即归零，不再误报
    const streakMs = activeStreakMs(t)
    if (streakMs >= 90 * 60_000) lines.push(pick(MSG_BREAK_LONG(fmtDuration(streakMs)), seed))
    else if (streakMs >= 45 * 60_000) lines.push(pick(MSG_BREAK_SHORT(fmtDuration(streakMs)), seed))
    if (doneToday.length && !overdue.length) lines.push(pick(MSG_PRAISE(doneToday.length), seed))

    return { title: slot.title, icon: slot.icon, tone: slot.tone, mood, lines: lines.slice(0, 3) }
  })

  return { warm }
}
