<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useHelpStore } from '../../stores/help'
import { GUIDES } from '../../content/guides'

const help = useHelpStore(), router = useRouter(), route = useRoute()
const titles = ['欢迎使用知时', '点这里，新建一条待办', '写下你要做的事', '点“创建”，保存到看板', '保存成功，在这里能找到它', '这里是日历', '想让 AI 帮忙？', '已经会用了，慢慢探索吧']
const descriptions = [
  '接下来会用亮框和箭头指着实际按钮，带你保存一条待办。鼠标左键点一下就是“点击”。无需先配置 AI，随时可以退出。',
  '用鼠标左键点击亮框中的“新建任务”。点击后，会出现填写任务的输入框。',
  '点击亮框中的输入框，写一件真正要做的事，例如“取快递”。日期和优先级可以先不改。写好后，点本提示中的“填好了”。',
  '点击亮框中的“创建”。等它保存成功，指引会自动继续。也可以按 Enter 保存。若页面提示失败，请先核对提示和看板中的记录。',
  '这就是刚才保存的真实待办。真正做完后，点任务前面的圆圈可标为完成；误点可以再点一次取消。现在先不用勾选。',
  '左侧这个图标打开日历，可以看已经安排好时间的事情。普通待办会留在看板，填写标题并不会自动把它排进日历。',
  '从“设置 → AI 模型”添加并启用配置，就能在对话区提要求。需要同一服务商的密钥、基础地址、模型名称和接口格式；没有这些资料也能继续手动使用。',
  '忘记步骤时，点顶部“使用教程”；想再学一遍，在教程里点“新手指引”。接入 AI 后，先发一句“你好”，再试试“列出我的待办任务”。',
]
const card = ref<HTMLElement | null>(null)
const target = ref<HTMLElement | null>(null)
const ready = ref(false)
const viewport = ref({ w: innerWidth, h: innerHeight })
const hole = ref<{ x: number; y: number; w: number; h: number } | null>(null)
const position = ref({ left: '16px', top: '16px' })
const arrow = ref('')
const missing = computed(() => help.tourStep > 0 && help.tourStep < 7 && !target.value)
let timer: ReturnType<typeof setInterval> | undefined
let previousFocus: HTMLElement | null = null
let lastTarget: HTMLElement | null = null
let navigating = false

function selector() {
  return ['', '[data-tour="new-task"]', '[data-tour="task-title"]', '[data-tour="create-task"]',
    `[data-tour-task="${help.createdTaskId}"]`, '[data-tour="nav-calendar"]', '[data-tour="nav-settings"]', ''][help.tourStep] ?? ''
}
function update() {
  if (!help.tourOpen) return
  const step = help.tourStep
  const title = document.querySelector<HTMLInputElement>('[data-tour="task-title"]')
  if (!navigating && route.path === '/board') {
    if (step === 1 && title) help.tourStep = 2
    else if ((step === 2 || step === 3) && !title) help.tourStep = 1
  }
  ready.value = !!title?.value.trim()
  const query = selector()
  const el = query ? document.querySelector<HTMLElement>(query) : null
  const rect = el?.getBoundingClientRect()
  target.value = rect && rect.width && rect.height ? el : null
  if (target.value && lastTarget !== target.value) {
    target.value.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' })
    lastTarget = target.value
  }
  const w = innerWidth, h = innerHeight
  viewport.value = { w, h }
  const r = target.value?.getBoundingClientRect()
  const x = Math.max(4, (r?.left ?? 4) - 5), y = Math.max(4, (r?.top ?? 4) - 5)
  hole.value = r ? { x, y, w: Math.max(0, Math.min(w - 4, r.right + 5) - x), h: Math.max(0, Math.min(h - 4, r.bottom + 5) - y) } : null
  const cw = card.value?.offsetWidth ?? Math.min(360, w - 24), ch = card.value?.offsetHeight ?? 300
  let left = (w - cw) / 2, top = (h - ch) / 2
  const t = hole.value
  if (t) {
    if (h - t.y - t.h >= ch + 32) { left = t.x; top = t.y + t.h + 24 }
    else if (t.y >= ch + 32) { left = t.x; top = t.y - ch - 24 }
    else if (w - t.x - t.w >= cw + 32) { left = t.x + t.w + 24; top = t.y }
    else if (t.x >= cw + 32) { left = t.x - cw - 24; top = t.y }
    else { top = h - ch - 12; left = (w - cw) / 2 }
  }
  left = Math.max(12, Math.min(w - cw - 12, left)); top = Math.max(12, Math.min(h - ch - 12, top))
  position.value = { left: `${left}px`, top: `${top}px` }
  if (t) {
    const tx = t.x + t.w / 2, ty = t.y + t.h / 2
    const sx = Math.max(left + 18, Math.min(left + cw - 18, tx))
    const sy = ty < top ? top : ty > top + ch ? top + ch : top + ch / 2
    const ex = tx < left ? t.x + t.w : tx > left + cw ? t.x : tx
    const ey = ty < top ? t.y + t.h : ty > top + ch ? t.y : ty
    arrow.value = `M ${sx} ${sy} L ${ex} ${ey}`
  } else arrow.value = ''
}
async function begin() {
  navigating = true
  try { await router.push('/board'); help.tourStep = 1; await nextTick() }
  finally { navigating = false; update() }
}
function next() { help.tourStep = Math.min(7, help.tourStep + 1) }
function openApi() { help.openGuide('api', Math.max(0, GUIDES.api.findIndex(s => s.title === '一步步配置'))) }
async function configure() {
  const saving = help.finishTour('completed')
  await router.push('/settings?section=configs')
  await saving
}
function keydown(event: KeyboardEvent) {
  if (!help.tourOpen) return
  // Keep application shortcuts from interpreting the guide's keyboard actions.
  if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); void help.finishTour('skipped'); return }
  if (event.key !== 'Tab') return
  const controls = [...(card.value?.querySelectorAll<HTMLElement>('button:not(:disabled)') ?? [])]
  if (help.tourStep !== 4 && target.value?.matches('button:not(:disabled), input, a')) controls.unshift(target.value)
  if (!controls.length) return
  const current = controls.indexOf(document.activeElement as HTMLElement)
  const index = (current + (event.shiftKey ? -1 : 1) + controls.length) % controls.length
  event.preventDefault(); event.stopImmediatePropagation(); controls[index]?.focus()
}
watch(() => help.tourOpen, async open => {
  if (timer) clearInterval(timer)
  document.removeEventListener('keydown', keydown, true)
  if (open) {
    previousFocus = document.activeElement as HTMLElement
    await nextTick()
    if (!help.tourOpen) return
    update(); card.value?.focus()
    document.addEventListener('keydown', keydown, true)
    timer = setInterval(update, 120)
  } else if (!help.guideOpen && previousFocus?.isConnected) previousFocus.focus()
}, { immediate: true, flush: 'post' })
watch(() => help.tourStep, async () => { await nextTick(); update(); card.value?.focus() })
onBeforeUnmount(() => { if (timer) clearInterval(timer); document.removeEventListener('keydown', keydown, true) })
</script>

<template>
  <Teleport to="body">
    <div v-if="help.tourOpen" class="guided-tour">
      <template v-if="hole">
        <div class="shade" :style="{ left: 0, top: 0, width: '100%', height: `${hole.y}px` }" />
        <div class="shade" :style="{ left: 0, top: `${hole.y}px`, width: `${hole.x}px`, height: `${hole.h}px` }" />
        <div class="shade" :style="{ left: `${hole.x + hole.w}px`, top: `${hole.y}px`, right: 0, height: `${hole.h}px` }" />
        <div class="shade" :style="{ left: 0, top: `${hole.y + hole.h}px`, width: '100%', bottom: 0 }" />
        <div class="spotlight" :style="{ left: `${hole.x}px`, top: `${hole.y}px`, width: `${hole.w}px`, height: `${hole.h}px` }" />
      </template>
      <div v-else class="shade full" />
      <svg v-if="arrow" class="tour-arrow" :viewBox="`0 0 ${viewport.w} ${viewport.h}`" aria-hidden="true">
        <defs><marker id="tour-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M 0 0 L 7 4 L 0 8" fill="none" stroke="currentColor" stroke-width="1.5" /></marker></defs>
        <path :d="arrow" fill="none" stroke="currentColor" stroke-width="2" marker-end="url(#tour-arrowhead)" />
      </svg>
      <section ref="card" class="tour-card" :style="position" role="dialog" aria-label="新手指引" aria-describedby="tour-description" tabindex="-1" @keydown.stop>
        <header><span>新手指引 · {{ help.tourStep + 1 }} / {{ titles.length }}</span><button aria-label="关闭新手指引" @click="help.finishTour('skipped')">×</button></header>
        <h2 aria-live="polite">{{ titles[help.tourStep] }}</h2>
        <p id="tour-description">{{ descriptions[help.tourStep] }}</p>
        <p v-if="missing" class="hint" role="status">当前没找到对应控件。可返回看板重试，或跳过这一步。</p>
        <div v-if="help.tourStep === 6" class="extra"><button @click="openApi">先看 AI 接入教程</button><button @click="configure">打开 AI 模型设置 ↗</button></div>
        <footer>
          <button class="skip" @click="help.finishTour('skipped')">暂时跳过</button>
          <button v-if="help.tourStep === 0 || missing && help.tourStep < 5" class="primary" @click="begin">{{ help.tourStep === 0 ? '开始，一步步来' : '返回看板重试' }}</button>
          <button v-else-if="help.tourStep === 2" class="primary" :disabled="!ready" @click="next">填好了 →</button>
          <button v-else-if="help.tourStep === 1 || help.tourStep === 3" @click="help.tourStep = 5">跳过练习 →</button>
          <button v-else-if="help.tourStep === 7" class="primary" @click="help.finishTour('completed')">开始使用</button>
          <button v-else class="primary" @click="next">下一步 →</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.guided-tour { position:fixed; inset:0; z-index:100; pointer-events:none; }
.shade { position:fixed; background:rgba(0,0,0,.48); pointer-events:auto; }
.full { inset:0; }
.spotlight { position:fixed; border:2px solid var(--amber-soft); border-radius:7px; box-shadow:0 0 0 3px var(--amber-wash); }
.tour-arrow { position:fixed; inset:0; width:100%; height:100%; color:var(--amber-soft); overflow:visible; }
.tour-card { position:fixed; width:360px; max-width:calc(100vw - 24px); max-height:calc(100dvh - 24px); overflow:auto; padding:18px 20px; border:1px solid var(--line-2); border-radius:12px; background:var(--bg-raise); color:var(--ink); box-shadow:var(--shadow-panel); pointer-events:auto; }
.tour-card:focus { outline:none; }
header { display:flex; justify-content:space-between; align-items:center; gap:12px; color:var(--ink-3); font-size:12px; }
header button { width:30px; height:30px; font-size:22px; }
h2 { font:600 22px/1.5 var(--serif); margin:10px 0; }
p { font-size:14px; line-height:1.9; color:var(--ink-2); margin:0 0 16px; }
.hint { color:var(--amber-soft); font-size:12px; }
footer { display:flex; align-items:center; gap:8px; flex-wrap:wrap; border-top:1px solid var(--line); padding-top:12px; }
button { min-height:36px; padding:7px 10px; border-radius:7px; color:var(--ink-2); font-size:13px; }
button:hover { background:var(--ink-wash); }
button:disabled { opacity:.45; cursor:not-allowed; }
button:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }
.skip { margin-right:auto; color:var(--ink-3); padding-left:0; }
.primary { background:var(--amber-wash-strong); color:var(--amber-soft); border:1px solid var(--amber-border); font-weight:600; }
.extra { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }.extra button { border:1px solid var(--line-2); }
@media(max-height:540px) { .tour-card { padding:12px 16px; width:330px; }h2 { font-size:18px; margin:4px 0; }p { font-size:13px; line-height:1.6; margin-bottom:10px; } }
</style>
