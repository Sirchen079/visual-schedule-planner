// 暖心个性化提醒：根据当前时间、任务安排与连续使用时长，生成温和的中文提示。
// 纯前端派生：任务数据来自看板 props，时长取本次会话连续使用时间（sessionStorage 记录起点），
// 每分钟重新评估一次，无需后端配合。
// 文案采用多句池 + 按天轮换（种子=当天）：同一天内内容稳定不跳动，第二天自动换一批说法。
import { computed, ref } from 'vue'

const now = ref(Date.now())
setInterval(() => (now.value = Date.now()), 60_000)

const SESSION_KEY = 'zhishi_session_start'
function sessionStart() {
  let ts = Number(sessionStorage.getItem(SESSION_KEY))
  // 没有记录或记录异常（未来/超过 12 小时前）时重置为现在
  if (!ts || ts > Date.now() || Date.now() - ts > 12 * 3600_000) {
    ts = Date.now()
    sessionStorage.setItem(SESSION_KEY, String(ts))
  }
  return ts
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

// ---- 文案池 ----

// 深夜（23:00–05:00）：主线只谈休息，不制造焦虑
const LATE_NIGHT = [
  '夜深了，早点休息，别熬夜。',
  '这个点了，身体比任务更需要你。去睡吧。',
  '夜很安静，适合放下，不适合硬撑。晚安。',
]
const LATE_NIGHT_DONE = (n) => [
  `今天已经完成了 ${n} 项任务，带着这份踏实感安心睡吧。`,
  `今天搞定 ${n} 项任务，很不错了。睡个好觉，明天见。`,
]
const LATE_NIGHT_TODO = [
  '还没做完的事先记下来，明天精神饱满地处理，效率会更高。',
  '把没做完的事交给明天，今晚会睡得更安稳。',
]

// 时段暖心句
const TIME_SLOTS = [
  {
    from: 5, to: 9, title: '早上好', icon: 'sun', tone: 'sand',
    lines: [
      '一日之计在于晨。趁头脑最清醒，把最重要的事放在前面。',
      '早安。新的一天，先深呼吸，再想想今天最想完成的三件事。',
      '清晨的效率是一天里最高的，别辜负了它。',
    ],
  },
  {
    from: 9, to: 11, title: '上午好', icon: 'sun', tone: 'aqua',
    lines: [
      '上午正是专注的好时候，适合啃最难的那块骨头。',
      '趁精力满格，先处理最需要动脑的事。',
      '上午好。专注一小时，胜过分心一上午。',
    ],
  },
  {
    from: 11, to: 13, title: '中午好', icon: 'sun', tone: 'sand',
    lines: [
      '忙了一上午，记得按时吃饭、稍微歇一会儿，下午才有精神。',
      '中午好。先放下手里的事，好好吃顿饭。',
      '饭后眯十五分钟，下午的效率会翻倍。',
    ],
  },
  {
    from: 13, to: 18, title: '下午好', icon: 'sun', tone: 'aqua',
    lines: [
      '下午容易犯困，泡杯茶站起来走走，节奏缓一点也没关系。',
      '下午好。离收工不远了，看看今天还能收尾哪一件。',
      '困了就活动一下肩颈，别硬扛着盯屏幕。',
    ],
  },
  {
    from: 18, to: 23, title: '晚上好', icon: 'moon', tone: 'aqua',
    lines: [
      '忙了一天辛苦了。晚上的时间，记得留一点给自己。',
      '晚上好。今天的事尽力就好，剩下的交给明天。',
      '吃点好的，陪陪家人，或者安静看会儿书——晚上属于你。',
    ],
  },
]

// 任务情境句（函数接收数量 n）
const MSG_OVERDUE = (n) => [
  `有 ${n} 项任务已经逾期。别焦虑，挑最小的一项，现在开始就不晚。`,
  `${n} 项任务过了期限。没关系，从今天重新开始推进它们。`,
  `逾期的 ${n} 项任务在等你。先处理拖得最久的那个，会轻松一大截。`,
]
const MSG_DUE_TODAY = (n) => [
  `今天有 ${n} 项任务到期。优先处理它们，其他的事可以先放一放。`,
  `${n} 项任务今天截止。集中注意力，一件一件来。`,
  `今天的截止任务有 ${n} 项，完成后会特别有成就感。`,
]
const MSG_DUE_TOMORROW = (n) => [
  `明天有 ${n} 项任务到期。今天先铺垫一小步，明天会轻松很多。`,
  `${n} 项任务明天截止，今天先给它开个头吧。`,
]
const MSG_EMPTY = [
  '新的一天从第一个任务开始——用右侧的快速新建，把脑海里的事先记下来吧。',
  '看板还是空的。把挂念的事写下来，大脑就轻松了。',
]
const MSG_ALL_CLEAR = [
  '手头没有待办任务，难得的空档。可以整理资料，或者干脆给自己放个假。',
  '任务全部完成，干得漂亮。好好享受这份清爽。',
]
const MSG_DOING = (n) => [
  `有 ${n} 项任务正在推进。保持节奏，稳扎稳打就很好。`,
  `${n} 项任务在路上。不着急，持续小步前进就是快。`,
]
const MSG_DEFAULT = [
  '任务都安排妥当了。挑一件最重要的，先从五分钟开始。',
  '一切尽在掌握。现在，从最重要的一件开始。',
]

// 完成肯定 / 休息提醒
const MSG_PRAISE = (n) => [
  `今天已完成 ${n} 项任务，这份进展值得肯定。`,
  `今天已经搞定 ${n} 项了，给自己一个肯定的眼神。`,
]
const MSG_BREAK_LONG = (d) => [
  `已经连续工作 ${d} 了。认真很值得，但休息也是效率的一部分——起来活动五分钟吧。`,
  `专注 ${d} 了，身体该充电了。站起来倒杯水，看看窗外。`,
]
const MSG_BREAK_SHORT = (d) => [
  `已经专注 ${d} 了，倒杯水、眺望一下远处吧。`,
  `工作 ${d} 了，眨眨眼、伸个懒腰再继续。`,
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

    // 副线：休息提醒（健康优先，排在完成肯定之前）
    const sessionMs = t - sessionStart()
    if (sessionMs >= 90 * 60_000) lines.push(pick(MSG_BREAK_LONG(fmtDuration(sessionMs)), seed))
    else if (sessionMs >= 45 * 60_000) lines.push(pick(MSG_BREAK_SHORT(fmtDuration(sessionMs)), seed))
    if (doneToday.length && !overdue.length) lines.push(pick(MSG_PRAISE(doneToday.length), seed))

    return { title: slot.title, icon: slot.icon, tone: slot.tone, mood, lines: lines.slice(0, 3) }
  })

  return { warm }
}
