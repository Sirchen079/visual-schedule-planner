<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useHelpStore } from '../../stores/help'
import { GUIDES } from '../../content/guides'
import { FEATURE_LESSONS, FEATURE_START, TOUR_END } from '../../content/features'

const help = useHelpStore(), router = useRouter(), route = useRoute()
const titles = ['欢迎使用知时', '点这里，新建一条待办', '写下你要做的事', '点“创建”，保存到看板', '保存成功，在这里能找到它']
const descriptions = [
  '跟着亮框和箭头，试着记一条待办。也可以点“先去使用”，以后从教程里继续。',
  '点击亮框中的“新建任务”，打开输入框。',
  '在输入框写下要做的事，例如“取快递”。日期和优先级可以先不改。写好后点“填好了”。',
  '点击“创建”或按 Enter 保存，成功后指引会自动继续。如果保存失败，按页面提示重试。',
  '任务已经保存在看板上。做完后点前面的圆圈标记完成，误点可以再点一次取消。',
]
const card = ref<HTMLElement | null>(null)
const collapsed = ref(false)
const feature = computed(() => FEATURE_LESSONS[help.tourStep - FEATURE_START])
const heading = computed(() => feature.value ? `${feature.value.name} · ${help.tourPhase === 'entry' ? '用来做什么' : '从哪里开始'}` : help.tourStep === TOUR_END ? '随时回来，按需要继续学' : titles[help.tourStep])
const description = computed(() => feature.value?.purpose ?? (help.tourStep === TOUR_END ? `已看过 ${help.seenFeatures.length} / ${FEATURE_LESSONS.length} 个栏目。可以从目录补学，也可以开始使用；顶部“使用教程”能随时找回完整说明。` : descriptions[help.tourStep]))
const target = ref<HTMLElement | null>(null)
const ready = ref(false)
const viewport = ref({ w: innerWidth, h: innerHeight })
const hole = ref<{ x: number; y: number; w: number; h: number } | null>(null)
const position = ref({ left: '16px', top: '16px' })
const arrow = ref('')
const missing = computed(() => help.tourStep > 0 && help.tourStep < TOUR_END && !target.value)
let timer: ReturnType<typeof setInterval> | undefined
let previousFocus: HTMLElement | null = null
let lastTarget: HTMLElement | null = null
let navigating = false

function selector() {
  if (feature.value) {
    const selectors = help.tourPhase === 'page' ? feature.value.targets
      : feature.value.id === 'chat' ? ['.nav-chat-toggle', '.chat-head'] : [`[data-tour="nav-${feature.value.id}"]`]
    return selectors.find(query => [...document.querySelectorAll<HTMLElement>(query)].some(el => el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0)) ?? ''
  }
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
function next() {
  if (feature.value) help.markFeatureRead(feature.value.id)
  help.tourStep = Math.min(TOUR_END, help.tourStep + 1); help.tourPhase = 'entry'
}
async function openFeature() {
  if (feature.value?.path) await router.push(feature.value.path)
  help.tourPhase = 'page'; await nextTick(); update()
}
function jump(event: Event) {
  const step = Number((event.target as HTMLSelectElement).value)
  if (step === 0) { help.tourStep = 0; help.tourPhase = 'entry' }
  else { const lesson = FEATURE_LESSONS[step - FEATURE_START]; if (lesson) help.startFeatureTour(lesson.id) }
}
function openArticle() {
  const section = GUIDES.usage.findIndex(s => s.title === feature.value?.article)
  help.openGuide('usage', Math.max(0, section))
}
function clicked(event: MouseEvent) {
  if (feature.value && help.tourPhase === 'entry' && target.value?.contains(event.target as Node)) void openFeature()
}
function openApi() { help.openGuide('api', Math.max(0, GUIDES.api.findIndex(s => s.title === '一步步配置'))) }
function keydown(event: KeyboardEvent) {
  if (!help.tourOpen) return
  if (collapsed.value) return
  // Keep application shortcuts from interpreting the guide's keyboard actions.
  if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); void help.finishTour('skipped'); return }
  if (event.key !== 'Tab') return
  const focusable = 'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]'
  const controls = [...(card.value?.querySelectorAll<HTMLElement>(focusable) ?? [])]
  if (help.tourStep !== 4) controls.unshift(...[...(target.value?.querySelectorAll<HTMLElement>(focusable) ?? [])].filter(el => el.getBoundingClientRect().width > 0))
  if (help.tourStep !== 4 && target.value?.matches('button:not(:disabled), input, a')) controls.unshift(target.value)
  if (!controls.length) return
  const current = controls.indexOf(document.activeElement as HTMLElement)
  const index = (current + (event.shiftKey ? -1 : 1) + controls.length) % controls.length
  event.preventDefault(); event.stopImmediatePropagation(); controls[index]?.focus()
}
watch(() => help.tourOpen, async open => {
  if (timer) clearInterval(timer)
  document.removeEventListener('keydown', keydown, true)
  document.removeEventListener('click', clicked)
  if (open) {
    previousFocus = document.activeElement as HTMLElement
    await nextTick()
    if (!help.tourOpen) return
    update(); card.value?.focus()
    document.addEventListener('keydown', keydown, true)
    document.addEventListener('click', clicked)
    timer = setInterval(update, 120)
  } else if (!help.guideOpen && previousFocus?.isConnected) previousFocus.focus()
}, { immediate: true, flush: 'post' })
watch(() => [help.tourStep, help.tourPhase, collapsed.value], async () => { await nextTick(); update(); card.value?.focus() })
watch(() => [help.tourStep, help.tourPhase], () => {
  collapsed.value = false
  card.value?.querySelector('.tour-content')?.scrollTo(0, 0)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer); document.removeEventListener('keydown', keydown, true); document.removeEventListener('click', clicked) })
</script>

<template>
  <Teleport to="body">
    <div v-if="help.tourOpen" class="guided-tour">
      <button v-if="collapsed" class="resume-lesson" @click="collapsed = false">返回“{{ feature?.name }}”指引 ↑</button>
      <template v-if="hole && !collapsed">
        <div class="shade" :style="{ left: 0, top: 0, width: '100%', height: `${hole.y}px` }" />
        <div class="shade" :style="{ left: 0, top: `${hole.y}px`, width: `${hole.x}px`, height: `${hole.h}px` }" />
        <div class="shade" :style="{ left: `${hole.x + hole.w}px`, top: `${hole.y}px`, right: 0, height: `${hole.h}px` }" />
        <div class="shade" :style="{ left: 0, top: `${hole.y + hole.h}px`, width: '100%', bottom: 0 }" />
        <div class="spotlight" :style="{ left: `${hole.x}px`, top: `${hole.y}px`, width: `${hole.w}px`, height: `${hole.h}px` }" />
      </template>
      <div v-else-if="!collapsed" class="shade full" />
      <svg v-if="arrow && !collapsed" class="tour-arrow" :viewBox="`0 0 ${viewport.w} ${viewport.h}`" aria-hidden="true">
        <defs><marker id="tour-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M 0 0 L 7 4 L 0 8" fill="none" stroke="currentColor" stroke-width="1.5" /></marker></defs>
        <path :d="arrow" fill="none" stroke="currentColor" stroke-width="2" marker-end="url(#tour-arrowhead)" />
      </svg>
      <section v-if="!collapsed" ref="card" class="tour-card" :style="position" role="dialog" aria-label="新手指引" aria-describedby="tour-description" tabindex="-1" @keydown.stop>
        <header><span>新手指引 · 栏目已读 {{ help.seenFeatures.length }} / {{ FEATURE_LESSONS.length }}</span><button aria-label="关闭新手指引" @click="help.finishTour('skipped')">×</button></header>
        <label v-if="help.tourStep === 0 || help.tourStep >= FEATURE_START" class="tour-directory">学习目录<select aria-label="学习目录" :value="help.tourStep < FEATURE_START || help.tourStep === TOUR_END ? '' : help.tourStep" @change="jump"><option value="" disabled>选择练习或栏目，可随时跳转</option><option value="0">基础练习：保存第一条待办</option><option v-for="(lesson, index) in FEATURE_LESSONS" :key="lesson.id" :value="FEATURE_START + index">{{ help.seenFeatures.includes(lesson.id) ? '✓ ' : '' }}{{ index + 1 }}. {{ lesson.name }}</option></select></label>
        <div class="tour-content">
        <h2 aria-live="polite">{{ heading }}</h2>
        <p id="tour-description">{{ description }}</p>
        <template v-if="feature">
          <p v-if="help.tourPhase === 'entry'" class="example">{{ feature.example }}</p>
          <ol v-else class="lesson-steps"><li v-for="step in feature.steps" :key="step">{{ step }}</li></ol>
          <div class="extra"><button @click="openArticle">完整操作教程</button><button v-if="feature.id === 'settings' || feature.id === 'chat'" @click="openApi">AI 接入教程</button></div>
          <button v-if="help.tourPhase === 'page'" class="practice-toggle" @click="collapsed = true">收起提示，按步骤操作 ↘</button>
        </template>
        <p v-if="missing" class="hint" role="status">{{ feature ? '当前入口可能未显示。可以用下方按钮打开栏目，或查看完整操作教程。' : '当前没找到对应控件。可返回看板重试，或从目录选择栏目。' }}</p>
        </div>
        <footer>
          <button class="skip" @click="help.finishTour('skipped')">先去使用</button>
          <button v-if="help.tourStep === 2" @click="help.tourStep = FEATURE_START">跳过练习</button>
          <template v-if="feature"><button v-if="help.tourPhase === 'entry'" class="primary" @click="openFeature">打开栏目，跟着学 →</button><button v-else class="primary" @click="next">看过了，{{ help.tourStep === TOUR_END - 1 ? '完成本次学习' : '下一栏目' }} →</button></template>
          <button v-else-if="help.tourStep === 0 || missing && help.tourStep < 5" class="primary" @click="begin">{{ help.tourStep === 0 ? '开始，一步步来' : '返回看板重试' }}</button>
          <button v-else-if="help.tourStep === 2" class="primary" :disabled="!ready" @click="next">填好了 →</button>
          <button v-else-if="help.tourStep === 1 || help.tourStep === 3" @click="help.tourStep = 5">跳过练习 →</button>
          <button v-else-if="help.tourStep === TOUR_END" class="primary" @click="help.finishTour('completed')">开始使用</button>
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
.tour-card { position:fixed; display:flex; flex-direction:column; width:360px; max-width:calc(100vw - 24px); max-height:calc(100dvh - 24px); overflow:hidden; padding:18px 20px; border:1px solid var(--line-2); border-radius:12px; background:var(--bg-raise); color:var(--ink); box-shadow:var(--shadow-panel); pointer-events:auto; }
.tour-content { min-height:0; overflow:auto; }
.tour-card > header,.tour-card > footer,.tour-directory { flex:none; }
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
.tour-directory { display:block; font-size:12px; color:var(--ink-3); margin-top:10px; }.tour-directory select { display:block; width:100%; margin-top:5px; padding:8px; border:1px solid var(--line-2); border-radius:7px; background:var(--bg-sink); color:var(--ink); }
.resume-lesson { position:fixed; bottom:20px; right:20px; max-width:calc(100vw - 40px); pointer-events:auto; background:var(--bg-raise); color:var(--amber-soft); border:1px solid var(--amber-border); box-shadow:var(--shadow-panel); }.practice-toggle { margin:0 0 12px; color:var(--amber-soft); }
.lesson-steps { list-style:decimal; padding-left:20px; font-size:13px; line-height:1.8; color:var(--ink-2); margin-bottom:14px; }.lesson-steps li { margin:6px 0; }.example { font-size:13px; }
@media(max-height:540px) { .tour-card { padding:12px 16px; width:330px; }h2 { font-size:18px; margin:4px 0; }p { font-size:13px; line-height:1.6; margin-bottom:10px; } }
</style>
