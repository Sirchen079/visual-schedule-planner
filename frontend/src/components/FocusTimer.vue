<script setup>
// 悬浮专注计时器：番茄钟（默认 25 分钟）/ 正计时，fixed 左下，层级低于右下助手 FAB。
// 状态机 idle → running → break → idle；挂载时 getCurrentTimer() 恢复运行态（刷新/重启不丢）。
// 工作段落库成功后，若功能面板开了「伴随联动」，休息态会额外展示一句 AI 收束语（失败静默降级）。
// 唤起方式（两种都会进入 running）：
//   1) defineExpose 的 startFor(task, kind?)：组件内自调 startTimer + toast，供挂载方直接调用；
//   2) window 事件 'focus:start'（detail 为任务对象）：调用方（任务卡/弹窗）已自行
//      startTimer + toast，这里仅 getCurrentTimer() 同步状态，不重复开启计时。
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import ArtIcon from './ArtIcon.vue'
import { getCurrentTimer, startTimer, stopTimer } from '../api/timer'
import { timerSignoff } from '../api/ai'
import { getSettings } from '../api/settings'

const POMODORO_SEC = 25 * 60
const BREAK_SEC = 5 * 60
const EXTEND_SEC = 5 * 60

const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })

const state = ref('idle') // idle | running | break
const log = ref(null) // 当前运行中的 TimeLog
const now = ref(Date.now())
const extraSec = ref(0) // 本轮番茄手动延长的累计秒数（按 log.id 存 localStorage，刷新不丢）
const breakEndsAt = ref(0)
// 伴随联动：番茄钟收束语（功能面板「伴随联动」开关，挂载时读一次缓存）
const companionEnabled = ref(false)
const signoffText = ref('')
let ticker = null
let finishing = false // 结束/到点流程防重入

// ---- 时间推算：全部以 started_at 为基准本地计算，不轮询后端 ----
const isPomodoro = computed(() => log.value?.kind !== 'stopwatch')
const startedAt = computed(() => (log.value ? new Date(log.value.started_at).getTime() : 0))
const durationSec = computed(() => POMODORO_SEC + extraSec.value)
const elapsedSec = computed(() => Math.max(0, (now.value - startedAt.value) / 1000))
const remainSec = computed(() => Math.max(0, durationSec.value - elapsedSec.value))
const breakRemainSec = computed(() => Math.max(0, (breakEndsAt.value - now.value) / 1000))

const progress = computed(() => {
  if (state.value === 'break') return Math.min(1, 1 - breakRemainSec.value / BREAK_SEC)
  if (!isPomodoro.value) return (elapsedSec.value % 60) / 60 // 正计时：每分钟一圈的呼吸进度
  return Math.min(1, elapsedSec.value / durationSec.value)
})

function pad(n) {
  return String(n).padStart(2, '0')
}
// 剩余时间向上取整（开始即显示 25:00），已用时间向下取整；超 1 小时带小时位
function formatClock(totalSec) {
  const s = Math.round(totalSec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`
}

const timeLabel = computed(() => {
  if (state.value === 'break') return formatClock(Math.ceil(breakRemainSec.value))
  if (isPomodoro.value) return formatClock(Math.ceil(remainSec.value))
  return formatClock(Math.floor(elapsedSec.value))
})

// ---- 延长时间的本地持久化（刷新后仍记得本轮延长过） ----
function extraKey(id) {
  return `focus-extra-${id}`
}
function loadExtra(id) {
  try {
    return Math.max(0, Number(localStorage.getItem(extraKey(id))) || 0)
  } catch {
    return 0
  }
}
function saveExtra() {
  try {
    if (log.value) localStorage.setItem(extraKey(log.value.id), String(extraSec.value))
  } catch {
    // 隐私模式等：放弃持久化，不影响计时
  }
}
function clearExtra() {
  try {
    if (log.value) localStorage.removeItem(extraKey(log.value.id))
  } catch {
    // 同上
  }
}

// 与 useReminders 一致的 Web Notification 用法：仅 granted 时弹，API 不可用静默降级
function notify(title, body) {
  try {
    if (!window.Notification) return
    if (Notification.permission === 'granted') {
      new Notification(title, { body })
    } else if (Notification.permission === 'default') {
      Notification.requestPermission()
    }
  } catch {
    // 通知不可用时静默
  }
}

function applyRunning(newLog) {
  log.value = newLog
  extraSec.value = loadExtra(newLog.id)
  finishing = false
  now.value = Date.now()
  signoffText.value = ''
  state.value = 'running'
}

function resetToIdle() {
  state.value = 'idle'
  log.value = null
  extraSec.value = 0
  signoffText.value = ''
  finishing = false
}

function enterBreak() {
  state.value = 'break'
  breakEndsAt.value = Date.now() + BREAK_SEC * 1000
  now.value = Date.now()
}

// 伴随联动：工作段落库成功后取一句收束语，展示在休息态胶囊里；失败静默沿用静态文案
async function fetchSignoff(stoppedLog) {
  if (!companionEnabled.value || !stoppedLog?.id) return
  try {
    const res = await timerSignoff(stoppedLog.id)
    if (res?.text && state.value === 'break') signoffText.value = res.text
  } catch {
    // 静默降级：休息态仍显示「休息一下」
  }
}

// 番茄到点：落库 → 系统通知 → 进入休息
async function finishPomodoro() {
  if (finishing) return
  finishing = true
  const title = log.value?.task_title || ''
  let stopped = null
  try {
    stopped = await stopTimer()
  } catch {
    // 落库失败不阻塞休息流程；下次恢复时仍会同步到后端真实状态
  }
  clearExtra()
  notify('番茄钟完成', title)
  enterBreak()
  void fetchSignoff(stopped)
}

// 手动「结束」：落库后同样进入休息
async function manualFinish() {
  if (finishing) return
  finishing = true
  let stopped
  try {
    stopped = await stopTimer()
  } catch (e) {
    finishing = false
    toast.error(`结束计时失败：${e.message}`)
    return
  }
  clearExtra()
  enterBreak()
  void fetchSignoff(stopped)
}

function endBreak() {
  notify('休息结束', '可以开始下一轮专注了')
  resetToIdle()
}

function skipBreak() {
  resetToIdle()
}

function extend() {
  extraSec.value += EXTEND_SEC
  saveExtra()
  now.value = Date.now()
}

// 对外唤起：自调 startTimer，成功后进入 running（供挂载方 ref 调用）
async function startFor(task, kind = 'pomodoro') {
  if (!task?.id) return
  try {
    const newLog = await startTimer(task.id, kind)
    applyRunning(newLog)
    toast.success(`已开始专注《${task.title}》`)
  } catch (e) {
    toast.error(`开始专注失败：${e.message}`)
  }
}

// 'focus:start' 事件：调用方已完成 startTimer + toast，这里只同步后端状态
async function onFocusStart() {
  try {
    const cur = await getCurrentTimer()
    if (cur) applyRunning(cur)
  } catch {
    // 网络波动：保持现状
  }
}

function hintStart() {
  toast.info('在任务卡右键菜单或任务详情里选择「开始专注」')
}

function tick() {
  now.value = Date.now()
  if (state.value === 'running' && isPomodoro.value && remainSec.value <= 0) {
    finishPomodoro()
  } else if (state.value === 'break' && breakRemainSec.value <= 0) {
    endBreak()
  }
}

onMounted(async () => {
  ticker = setInterval(tick, 1000)
  window.addEventListener('focus:start', onFocusStart)
  // 伴随联动开关读取一次（功能面板「伴随联动」，默认关闭）
  getSettings()
    .then((s) => {
      companionEnabled.value = s.feature_companion_enabled === 'true'
    })
    .catch(() => {})
  // 恢复运行态：若番茄在离开期间已到点，tick 会自动走完结流程（落库+通知+休息）
  try {
    const cur = await getCurrentTimer()
    if (cur) applyRunning(cur)
  } catch {
    // 静默：保持 idle
  }
})

onUnmounted(() => {
  if (ticker) clearInterval(ticker)
  window.removeEventListener('focus:start', onFocusStart)
})

defineExpose({ startFor })
</script>

<template>
  <button
    v-if="state === 'idle'"
    type="button"
    class="focus-fab"
    title="开始专注"
    aria-label="开始专注"
    @click="hintStart"
  >
    <ArtIcon name="priority" tone="on-accent" :size="16" />
    <span>专注</span>
  </button>

  <div v-else class="focus-pill" :class="{ break: state === 'break' }" role="status">
    <div class="focus-info">
      <span class="focus-title" :title="log?.task_title || ''">
        {{ state === 'break' ? '休息一下' : log?.task_title || '专注中' }}
      </span>
      <span v-if="state === 'break' && signoffText" class="focus-signoff" :title="signoffText">
        幕僚：{{ signoffText }}
      </span>
      <span class="focus-time">{{ timeLabel }}</span>
      <span class="focus-track">
        <span class="focus-fill" :style="{ width: `${progress * 100}%` }"></span>
      </span>
    </div>
    <div class="focus-actions">
      <template v-if="state === 'running'">
        <button v-if="isPomodoro" type="button" class="focus-btn" title="本轮延长 5 分钟" @click="extend">
          +5分钟
        </button>
        <button type="button" class="focus-btn end" @click="manualFinish">结束</button>
      </template>
      <button v-else type="button" class="focus-btn" @click="skipBreak">跳过休息</button>
    </div>
  </div>
</template>

<style scoped>
/* 左下悬浮，与右下助手 FAB(z-index:210) 呼应且层级更低 */
.focus-fab {
  position: fixed;
  left: 28px;
  bottom: 28px;
  z-index: 190;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 40px;
  padding: 0 16px;
  border-radius: var(--radius-pill);
  border: none;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--accent), var(--sea-400));
  box-shadow: var(--shadow-lg), 0 0 18px var(--accent-glow);
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
}

.focus-fab:hover {
  transform: translateY(-2px);
  filter: saturate(1.04);
  box-shadow: var(--shadow-xl), 0 0 24px var(--accent-glow);
}

.focus-pill {
  position: fixed;
  left: 28px;
  bottom: 28px;
  z-index: 190;
  display: flex;
  align-items: center;
  gap: 14px;
  max-width: min(400px, calc(100vw - 56px));
  padding: 10px 12px 10px 14px;
  border-radius: var(--radius);
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-lg), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.focus-pill.break {
  border-color: color-mix(in srgb, var(--success) 34%, var(--border));
}

.focus-info {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.focus-title {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-soft);
}

.focus-signoff {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--text-soft);
  opacity: 0.85;
}

.focus-time {
  font-size: 20px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--accent-strong);
  line-height: 1.1;
}

.focus-pill.break .focus-time {
  color: var(--success);
}

.focus-track {
  display: block;
  width: 100%;
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--surface-3);
  overflow: hidden;
}

.focus-fill {
  display: block;
  height: 100%;
  border-radius: var(--radius-pill);
  background: linear-gradient(90deg, var(--accent), var(--sea-300));
  transition: width 0.6s linear;
}

.focus-pill.break .focus-fill {
  background: linear-gradient(90deg, var(--success), var(--foam-300));
}

.focus-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.focus-btn {
  padding: 6px 12px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.focus-btn:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent-hover);
}

.focus-btn.end:hover {
  border-color: color-mix(in srgb, var(--danger) 40%, var(--border));
  background: var(--danger-soft);
  color: var(--danger-strong);
}

@media (max-width: 720px) {
  .focus-fab,
  .focus-pill {
    left: 14px;
    bottom: 14px;
  }
}
</style>
