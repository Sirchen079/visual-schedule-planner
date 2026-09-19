<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import AppIcon from '../AppIcon.vue'
import { useFocusStore } from '../../stores/focus'

type NoticeKind = 'welcome' | 'rest'

const focus = useFocusStore()
const now = ref(Date.now())
let clockTimer: ReturnType<typeof setInterval> | null = null
const dismissedWelcome = ref('')
const dismissedRest = ref<number | null>(null)
const switching = ref(false)
const actionError = ref('')

const WELCOME_LINES: Array<[number, number, string, string]> = [
  [5, 9, '早安，愿今天的光落在你手边', '把最要紧的事交给清晨，慢慢来，也来得及。'],
  [9, 12, '上午好，思绪正适合向前', '先照顾眼前这一页，远处的答案会自己显出轮廓。'],
  [12, 14, '午间了，给自己留一小段空白', '吃点东西，望一望窗外，再把下午交还给自己。'],
  [14, 18, '下午好，光线还在', '不必急着把一天用尽，稳稳走完下一步就好。'],
  [18, 22, '晚上好，今天辛苦了', '把未完的事放在一旁，先听一听此刻的风。'],
  [22, 24, '夜深了，早点休息吧', '灯可以晚一点关，身体不要再往前赶了。'],
  [0, 5, '夜深了，愿你安睡', '把今天轻轻合上，明天还有新的页码。'],
]

const hour = computed(() => new Date(now.value).getHours())
const welcome = computed(() => {
  const item = WELCOME_LINES.find(([from, to]) => hour.value >= from && hour.value < to) ?? WELCOME_LINES[0]
  return { title: item[2], body: item[3] }
})
const dayKey = computed(() => {
  const date = new Date(now.value)
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`
})
const welcomeKey = computed(() => `${dayKey.value}-${WELCOME_LINES.findIndex(([from, to]) => hour.value >= from && hour.value < to)}`)
const restReady = computed(() =>
  focus.isRunning && focus.current?.kind !== 'break' && focus.elapsedSeconds >= 90 * 60,
)
const activeKind = computed<NoticeKind>(() => (restReady.value ? 'rest' : 'welcome'))
const visible = computed(() => {
  if (actionError.value) return true
  if (restReady.value) return dismissedRest.value !== focus.current?.id
  return dismissedWelcome.value !== welcomeKey.value
})
const title = computed(() => activeKind.value === 'rest' ? '该歇一歇了' : welcome.value.title)
const body = computed(() => activeKind.value === 'rest'
  ? '一个半小时已经走过去，眼睛和肩颈也该松一松了。去接一杯水，走到窗边，让思绪透口气。'
  : welcome.value.body)

function close(): void {
  actionError.value = ''
  if (activeKind.value === 'rest') {
    dismissedRest.value = focus.current?.id ?? null
    try { if (focus.current?.id) localStorage.setItem(`zhishi:rest-reminder:${focus.current.id}`, '1') } catch { /* 本次运行仍记住关闭状态 */ }
  } else {
    dismissedWelcome.value = welcomeKey.value
  }
}

async function startBreak(): Promise<void> {
  if (switching.value) return
  switching.value = true
  actionError.value = ''
  try {
    await focus.stop()
    if (focus.error) { actionError.value = focus.error; return }
    await focus.start('break', '短暂休息')
    if (focus.error) { actionError.value = focus.error; return }
    dismissedWelcome.value = welcomeKey.value
  } finally { switching.value = false }
}

function restoreDismissed(): void {
  const id = focus.current?.id
  try { dismissedRest.value = id && localStorage.getItem(`zhishi:rest-reminder:${id}`) ? id : null } catch { dismissedRest.value = null }
}

watch(() => focus.current?.id, restoreDismissed, { immediate: true })

onMounted(() => {
  // 时段只需分钟级精度；独立于壳层时钟，组件单独挂载时也能正确跨时段更新。
  clockTimer = setInterval(() => { now.value = Date.now() }, 60_000)
})
onUnmounted(() => {
  if (clockTimer !== null) clearInterval(clockTimer)
  clockTimer = null
})
</script>

<template>
  <Transition name="notice-slide">
    <aside v-if="visible" class="rest-notice" :data-kind="activeKind" role="status" aria-live="polite">
      <span class="notice-mark" aria-hidden="true"><AppIcon :name="activeKind === 'rest' ? 'timer' : 'spark'" :size="18" /></span>
      <div class="notice-copy">
        <strong>{{ title }}</strong>
        <p>{{ body }}</p>
        <p v-if="actionError" role="alert">{{ actionError }}</p>
      </div>
      <button v-if="activeKind === 'rest'" class="notice-action" type="button" :disabled="switching" @click="startBreak">{{ switching ? '正在切换…' : '开始休息' }}</button>
      <button class="notice-close" type="button" aria-label="关闭提示" title="关闭提示" :disabled="switching" @click="close"><AppIcon name="x" :size="15" /></button>
    </aside>
  </Transition>
</template>

<style scoped>
.rest-notice {
  position: fixed;
  top: 14px;
  left: 50%;
  z-index: 50;
  width: min(620px, calc(100vw - 32px));
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  color: var(--ink);
  background: color-mix(in srgb, var(--bg-raise) 94%, var(--amber) 6%);
  border: 1px solid var(--amber-border);
  border-radius: var(--radius-m);
  box-shadow: var(--shadow-panel), 0 0 0 1px var(--amber-wash);

}
.rest-notice[data-kind='rest'] { border-color: var(--amber); background: color-mix(in srgb, var(--bg-raise) 90%, var(--amber) 10%); }
.notice-mark { flex: none; width: 32px; height: 32px; display: grid; place-items: center; color: var(--amber-soft); background: var(--amber-wash); border-radius: var(--radius-s); }
.notice-copy { min-width: 0; flex: 1; }
.notice-copy strong { display: block; font-family: var(--serif); font-size: 15px; font-weight: 600; line-height: 1.35; }
.notice-copy p { margin-top: 4px; color: var(--ink-2); font-size: 14px; line-height: 1.6; }
.notice-action { flex: none; min-height: 36px; padding: 6px 11px; color: var(--btn-new-text); background: var(--btn-new-bg); border-radius: var(--radius-s); font-size: 12px; font-weight: 600; }
.notice-action:hover { background: var(--btn-new-bg-hover); }
.notice-close { flex: none; width: 36px; height: 36px; display: grid; place-items: center; color: var(--ink-3); border-radius: var(--radius-s); }
.notice-close:hover { color: var(--ink); background: var(--ink-wash); }
.notice-slide-enter-active, .notice-slide-leave-active { transition: opacity 180ms ease, transform 180ms ease; }
.notice-slide-enter-from, .notice-slide-leave-to { opacity: 0; transform: translate(-50%, -10px); }
@media (max-width: 640px) {
  .rest-notice { top: 8px; width: calc(100vw - 16px); padding: 10px; gap: 9px; }
  .notice-action { padding-inline: 8px; }
}
.rest-notice button:focus-visible { outline: 2px solid var(--amber); outline-offset: 3px; }
.rest-notice button:disabled { opacity: .7; cursor: wait; }
@media (max-width: 640px) {
  .rest-notice { flex-wrap: wrap; }
  .notice-action { margin-left: 44px; min-height: 44px; }
  .notice-close { width: 44px; height: 44px; }
  .notice-copy { flex-basis: calc(100% - 100px); }
}
</style>
