<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import GuidedTour from './GuidedTour.vue'
import GuideDialog from './GuideDialog.vue'
import { GUIDES, type GuidePage } from '../../content/guides'
import { useHelpStore } from '../../stores/help'
import { renderMarkdown } from '../../utils/md'

const help = useHelpStore(), router = useRouter()
const article = ref<HTMLElement | null>(null)
const guideSections = computed(() => GUIDES[help.page])
const selected = computed(() => guideSections.value[help.section] ?? guideSections.value[0]!)
const content = computed(() => renderMarkdown(selected.value.content))

function selectPage(page: GuidePage) { help.page = page; help.section = 0 }
function switchTab(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  selectPage(event.key === 'Home' ? 'usage' : event.key === 'End' ? 'api' : help.page === 'usage' ? 'api' : 'usage')
  void nextTick(() => document.getElementById(`guide-tab-${help.page}`)?.focus())
}
watch(() => [help.page, help.section], async () => {
  await nextTick()
  if (article.value) article.value.scrollTop = 0
})
async function configure() {
  const saving = help.returnToTour ? help.finishTour('completed') : Promise.resolve()
  help.closeGuide()
  await router.push('/settings?section=configs')
  await saving
}
</script>

<template>
  <GuideDialog :open="help.guideOpen" title="使用教程" wide @close="help.closeGuide()">
    <div class="guide-tabs" role="tablist" aria-label="教程类型" @keydown="switchTab">
      <button id="guide-tab-usage" role="tab" :aria-selected="help.page === 'usage'" aria-controls="guide-content"
        :tabindex="help.page === 'usage' ? 0 : -1" @click="selectPage('usage')">知时怎么用</button>
      <button id="guide-tab-api" role="tab" :aria-selected="help.page === 'api'" aria-controls="guide-content"
        :tabindex="help.page === 'api' ? 0 : -1" @click="selectPage('api')">AI 接入</button>
      <span class="offline-note">已内置 · 断网也能阅读</span>
    </div>
    <div class="guide-layout">
      <nav class="guide-contents" aria-label="教程目录">
        <span class="contents-label">想学哪一步，点这里</span>
        <button v-for="(section, index) in guideSections" :key="section.title"
          :aria-current="help.section === index ? 'page' : undefined" @click="help.section = index">
          <span>{{ String(index + 1).padStart(2, '0') }}</span>{{ section.title }}
        </button>
      </nav>
      <article id="guide-content" ref="article" class="guide-article" role="tabpanel" :aria-labelledby="`guide-tab-${help.page}`" tabindex="0">
        <p class="eyebrow">{{ help.page === 'api' ? '连接你自己的 AI' : '从第一件小事开始' }}</p>
        <h1>{{ selected.title }}</h1>
        <div class="guide-prose" v-html="content" />
        <div class="chapter-actions">
          <button v-if="help.section > 0" @click="help.section--">← 上一节</button>
          <button v-if="help.section < guideSections.length - 1" class="next-chapter" @click="help.section++">下一节：{{ guideSections[help.section + 1]?.title }} →</button>
        </div>
      </article>
    </div>
    <footer class="guide-footer">
      <button v-if="help.returnToTour" class="quiet-button" @click="help.closeGuide()">← 返回新手指引</button>
      <button v-else class="quiet-button" @click="help.startTour()">新手指引</button>
      <button v-if="help.page === 'api'" class="primary-button" @click="configure()">{{ help.returnToTour ? '结束引导，去配置 AI' : '打开 AI 模型设置' }} ↗</button>
      <button v-else class="primary-button" @click="help.closeGuide()">{{ help.returnToTour ? '看完了，继续引导' : '知道了，关闭教程' }}</button>
    </footer>
  </GuideDialog>

  <GuidedTour />

  <aside v-if="help.saveError" class="guide-save-warning" role="status"><p>{{ help.saveError }}</p><button :disabled="help.savingOutcome" @click="help.retrySaveOutcome()">{{ help.savingOutcome ? '正在保存…' : '重试保存' }}</button><button aria-label="关闭指引保存提示" @click="help.saveError = ''">×</button></aside>
</template>

<style scoped>
.guide-tabs { display:flex; align-items:center; gap:8px; flex:none; padding:12px 22px; border-bottom:1px solid var(--line); }
.guide-tabs button { padding:10px 18px; border-radius:7px; color:var(--ink-2); font-size:14px; }
.guide-tabs button[aria-selected=true] { background:var(--amber-wash-strong); color:var(--amber-soft); font-weight:600; }
.offline-note { margin-left:auto; font-size:12px; color:var(--ink-3); }
.guide-layout { display:flex; min-height:0; height:520px; max-height:60dvh; }
.guide-contents { width:232px; flex:none; overflow:auto; padding:20px 12px; border-right:1px solid var(--line); }
.contents-label { display:block; padding:0 10px 12px; color:var(--ink-3); font-size:12px; }
.guide-contents button { display:flex; align-items:baseline; gap:9px; width:100%; padding:10px; border-radius:7px; color:var(--ink-2); text-align:left; font-size:13px; line-height:1.6; }
.guide-contents button span { font-family:var(--mono); font-size:10px; color:var(--ink-3); }
.guide-contents button[aria-current=page] { color:var(--amber-soft); background:var(--amber-wash); }
.guide-article { min-width:0; flex:1; padding:28px 32px; overflow:auto; }
.eyebrow { color:var(--amber-soft); font-size:12px; letter-spacing:.08em; margin:0 0 10px; }
h1 { font-family:var(--serif); font-size:25px; line-height:1.4; font-weight:600; margin:0 0 22px; overflow-wrap:anywhere; }
.guide-prose { font-size:15px; line-height:1.95; color:var(--ink-2); overflow-wrap:anywhere; }
.guide-prose :deep(p) { margin:0 0 16px; }.guide-prose :deep(ul),.guide-prose :deep(ol) { padding-left:24px; margin:12px 0 20px; }.guide-prose :deep(ul) { list-style:disc; }.guide-prose :deep(ol) { list-style:decimal; }.guide-prose :deep(li) { margin:8px 0; }
.guide-prose :deep(strong) { color:var(--ink); font-weight:600; }.guide-prose :deep(a) { color:var(--amber-soft); text-decoration:underline; text-underline-offset:3px; }
.guide-prose :deep(table) { display:block; max-width:100%; overflow-x:auto; border-collapse:collapse; margin:16px 0 22px; font-size:13px; line-height:1.75; }.guide-prose :deep(td),.guide-prose :deep(th) { min-width:110px; border:1px solid var(--line-2); padding:10px; vertical-align:top; text-align:left; }.guide-prose :deep(th) { background:var(--bg-sink); font-weight:600; }
.guide-prose :deep(code) { font-family:var(--mono); font-size:.87em; background:var(--bg-sink); border:1px solid var(--line); border-radius:4px; padding:1px 4px; }.guide-prose :deep(pre) { overflow:auto; padding:12px; background:var(--bg-sink); }
.chapter-actions { display:flex; align-items:center; gap:20px; flex-wrap:wrap; padding-top:24px; border-top:1px solid var(--line); margin-top:28px; font-size:13px; color:var(--amber-soft); line-height:1.6; }.chapter-actions button { padding:8px 0; text-align:left; }.next-chapter { margin-left:auto; }
.guide-footer { flex:none; display:flex; justify-content:space-between; align-items:center; gap:12px; padding:16px 22px; border-top:1px solid var(--line); }
.primary-button,.quiet-button { display:inline-flex; align-items:center; justify-content:center; gap:6px; min-height:42px; padding:10px 16px; border-radius:7px; font-size:14px; line-height:1.5; }
.primary-button { color:var(--amber-soft); background:var(--amber-wash-strong); border:1px solid var(--amber-border); font-weight:600; }.primary-button:hover:not(:disabled) { background:var(--nav-hover-bg); }.quiet-button { border:1px solid var(--line-2); color:var(--ink-2); }.quiet-button:hover { background:var(--ink-wash); }
button:disabled { opacity:.5; cursor:not-allowed; }button:focus-visible,input:focus-visible,.guide-article:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }
.guide-save-warning { position:fixed; z-index:80; bottom:22px; left:80px; max-width:440px; display:flex; align-items:center; gap:14px; padding:16px; background:var(--bg-raise); border:1px solid var(--line-2); border-radius:10px; box-shadow:var(--shadow-panel); font-size:13px; }.guide-save-warning p { line-height:1.8; margin:0; }.guide-save-warning button { flex:none; color:var(--amber-soft); }
@media(max-width:700px) { .guide-layout { flex-direction:column; height:62dvh; max-height:none; }.guide-contents { width:auto; max-height:132px; padding:10px 12px; border-right:0; border-bottom:1px solid var(--line); display:flex; align-content:flex-start; flex-wrap:wrap; gap:4px; }.contents-label { width:100%; padding:0 4px 4px; }.guide-contents button { width:auto; padding:7px 9px; font-size:12px; }.guide-contents button span { display:none; }.guide-article { padding:22px 20px; }.offline-note { font-size:10px; }.guide-tabs { padding:10px 12px; gap:4px; }.guide-tabs button { padding:8px 12px; }.guide-footer { padding:12px 16px; }.tour-body { padding:24px 22px; }h1 { font-size:23px; }.tour-footer { padding:14px 18px; } }
@media(max-width:420px) { .tour-actions { flex-wrap:wrap; }.skip-button { order:3; width:100%; min-height:30px; text-align:center; }.tour-actions>.primary-button { flex:1; }.primary-button,.quiet-button { font-size:13px; padding:9px 12px; }.guide-footer { flex-wrap:wrap; }.guide-footer>.primary-button { flex:1; }.welcome-note,.ready-card { gap:14px; padding:16px; }.api-checklist dl>div { grid-template-columns:82px 1fr; }.tour-body { padding:22px 18px; }.practice-card { padding:16px; }.guide-save-warning { left:16px; right:16px; } }
</style>
