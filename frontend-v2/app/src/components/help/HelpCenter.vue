<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../AppIcon.vue'
import GuideDialog from './GuideDialog.vue'
import { GUIDES, TOUR_TITLES, type GuidePage } from '../../content/guides'
import { useHelpStore } from '../../stores/help'
import { renderMarkdown } from '../../utils/md'

const help = useHelpStore(), router = useRouter()
const article = ref<HTMLElement | null>(null), tourBody = ref<HTMLElement | null>(null)
const guideSections = computed(() => GUIDES[help.page])
const selected = computed(() => guideSections.value[help.section] ?? guideSections.value[0]!)
const content = computed(() => renderMarkdown(selected.value.content))
const lastStep = TOUR_TITLES.length - 1

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
watch(() => help.tourStep, async () => {
  await nextTick()
  if (tourBody.value) tourBody.value.scrollTop = 0
  tourBody.value?.querySelector<HTMLElement>('.tour-heading')?.focus()
})
function openApi(title: string) {
  help.openGuide('api', Math.max(0, GUIDES.api.findIndex(section => section.title === title)))
}
function nextStep() { help.tourStep = Math.min(lastStep, help.tourStep + 1) }
async function finish(path = '/board') {
  const saving = help.finishTour('completed')
  await router.push(path)
  await saving
}
async function configure() {
  if (help.returnToTour) { await finish('/settings?section=configs'); return }
  help.closeGuide()
  await router.push('/settings?section=configs')
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

  <GuideDialog :open="help.tourOpen" title="新手指引" @close="help.finishTour('skipped')">
    <div ref="tourBody" class="tour-body">
      <p class="eyebrow">不用着急，一次学一点</p>
      <h1 class="tour-heading" tabindex="-1" autofocus>{{ TOUR_TITLES[help.tourStep] }}</h1>

      <template v-if="help.tourStep === 0">
        <p class="tour-lead">把想做的事记下来，就不用一直惦记着。</p>
        <div class="welcome-note">
          <AppIcon name="journal" :size="36" />
          <div><strong>不熟悉电脑，也可以慢慢来。</strong><p>接下来会告诉你点哪里、填什么，还能一起保存第一条待办。</p></div>
        </div>
        <ol class="plain-steps">
          <li>“点击”就是用鼠标左键点一下。</li>
          <li>看完一页，点右下角“下一步”；没记住，可以点“上一步”。</li>
          <li>暂时不想看，点“暂时跳过”。以后从“使用教程 → 新手指引”再打开。</li>
        </ol>
        <p class="soft-note">不用付费或配置 AI，也能先手动使用待办等功能。</p>
      </template>

      <template v-else-if="help.tourStep === 1">
        <p class="tour-lead">主窗口最左边的小图标，是不同功能的入口。</p>
        <div class="place-list">
          <div><AppIcon name="board" :size="25" /><p><strong>看板 = 要做的事情</strong><span>比如交作业、取快递。新增、查看、勾选完成，都先到这里。</span></p></div>
          <div><AppIcon name="calendar" :size="25" /><p><strong>日历 = 已经排好的时间</strong><span>比如课程、开会。顶部点“日 / 周 / 月”切换查看范围。</span></p></div>
          <div><AppIcon name="settings" :size="25" /><p><strong>设置 = 调整软件</strong><span>通知、外观、AI 模型都在这里。暂时保持默认就可以。</span></p></div>
        </div>
        <p class="soft-note">不认识图标？把鼠标停在上面，稍等一下，就会显示名字。看清后再点。</p>
      </template>

      <template v-else-if="help.tourStep === 2">
        <p class="tour-lead">想一件你真正要做的事，写进下面的框里。</p>
        <form class="practice-card" @submit.prevent="help.savePractice()">
          <label for="first-task">① 点这里，输入待办名称</label>
          <input id="first-task" v-model="help.practiceTitle" maxlength="200" placeholder="例如：周五交英语作业"
            :disabled="help.practiceSaving || !!help.practiceTaskId || help.practiceUncertain" autocomplete="off" />
          <span class="input-note">这里只填名称即可；想不出要记什么，可以先跳过练习。</span>
          <button class="primary-button" type="submit" :disabled="!help.practiceTitle.trim() || help.practiceSaving || !!help.practiceTaskId || help.practiceUncertain">
            {{ help.practiceTaskId ? '已经保存 ✓' : help.practiceSaving ? '正在保存，请稍等…' : '② 保存这条待办' }}
          </button>
          <p v-if="help.practiceTaskId" class="practice-success" role="status"><AppIcon name="check" :size="18" />保存成功！关闭指引后，在“看板”里就能找到它。</p>
          <p v-if="help.practiceError" class="guide-error" role="alert">{{ help.practiceError }}</p>
        </form>
        <p class="soft-note">以后想再记一件事：左侧点“看板” → 页面上方点“新建任务” → 填标题 → 点“创建”。</p>
      </template>

      <template v-else-if="help.tourStep === 3">
        <p class="tour-lead">真正做完这件事后，再把它标为完成。</p>
        <div class="completion-example" aria-label="完成任务的操作示意">
          <span class="demo-label">操作示意</span>
          <div><span class="demo-circle"></span><span>{{ help.practiceTitle.trim() || '周五交英语作业' }}</span></div>
          <p>点任务前面的圆圈 ↓</p>
          <div class="example-done"><AppIcon name="check" :size="24" /><span>{{ help.practiceTitle.trim() || '周五交英语作业' }}</span><small>已完成</small></div>
        </div>
        <ol class="plain-steps"><li>先在“看板”找到任务。</li><li>做完了，点它前面的圆圈；按状态分组时，它会进入“已完成”一列。</li><li>误点了，再点一次就能取消完成。</li></ol>
        <p class="soft-note">上面只是示意。你刚保存的真实待办没有被勾选或修改。</p>
      </template>

      <template v-else-if="help.tourStep === 4">
        <p class="tour-lead">手动记录已经能用了。想让 AI 替你整理、安排时，再接入模型服务。</p>
        <div class="api-checklist"><strong>需要从同一个服务商准备这四项</strong>
          <dl><div><dt>API Key</dt><dd>你的接口密钥，像密码一样保管。</dd></div><div><dt>Base URL</dt><dd>服务商给的接口基础地址。</dd></div><div><dt>模型名称</dt><dd>准备调用哪个模型，按原样复制。</dd></div><div><dt>接口格式</dt><dd>服务商文档写明的格式，不靠猜。</dd></div></dl>
        </div>
        <div class="choice-actions"><button class="primary-button" @click="openApi('一步步配置')">已有资料，教我怎么填写</button><button class="quiet-button" @click="openApi('还没有账号或密钥，怎么办')">还没有，先了解一下</button></div>
        <p class="soft-note">暂时没有也没关系，直接点“下一步”。平时网页聊天的账号或订阅，不一定包含 API 额度。</p>
      </template>

      <template v-else-if="help.tourStep === 5">
        <p class="tour-lead">接入后，在对话区底部输入要求，再点右侧向上箭头发送。</p>
        <div class="sample-message"><span>可以这样说</span><p>“明天下午三点开会一小时，提前半小时提醒我。”</p></div>
        <div class="status-lessons"><div><strong>它在问问题</strong><p>点选项，必要时补充文字，再点“提交并继续”。</p></div><div><strong>它让你确认操作</strong><p>先看清要改什么、删什么。正确才同意，不对就拒绝。</p></div><div><strong>它说已经处理好了</strong><p>打开看板或日历，再核对一次事情和时间。等待时不用重复发送。</p></div></div>
        <p class="soft-note">窗口较窄、看不到输入框时，点左侧“对话”图标。想停止处理中任务，可以点输入区的停止按钮。</p>
      </template>

      <template v-else>
        <p class="tour-lead">不用一下记住。先用熟“记待办”和“勾选完成”就很好。</p>
        <div class="ready-card"><AppIcon name="check" :size="32" /><div><strong>{{ help.practiceTaskId ? '第一条待办已经在看板里了' : '下一步，去看板记一件事' }}</strong><p>点下面“开始使用，打开看板”，就能进入。</p></div></div>
        <ol class="plain-steps"><li>忘了步骤：点顶部“使用教程”，按目录找答案。</li><li>想再学一遍：点“使用教程 → 新手指引”。</li><li>想让 AI 帮忙：去“设置 → AI 模型”，按接入教程配置。</li></ol>
        <button class="quiet-button config-later" @click="finish('/settings?section=configs')">我准备好了，直接去配置 AI ↗</button>
      </template>
    </div>
    <footer class="tour-footer">
      <div class="tour-progress" aria-label="新手指引进度"><span>{{ help.tourStep + 1 }} / {{ TOUR_TITLES.length }}</span><div><i v-for="(_, index) in TOUR_TITLES" :key="index" :data-done="index <= help.tourStep" /></div></div>
      <div class="tour-actions">
        <button class="skip-button" :disabled="help.practiceSaving" @click="help.finishTour('skipped')">暂时跳过</button>
        <button v-if="help.tourStep > 0" class="quiet-button" :disabled="help.practiceSaving" @click="help.tourStep--">上一步</button>
        <button v-if="help.tourStep === lastStep" class="primary-button" @click="finish()">开始使用，打开看板</button>
        <button v-else class="primary-button" :disabled="help.practiceSaving" @click="nextStep()">{{ help.tourStep === 0 ? '开始，一步步来' : help.tourStep === 2 && !help.practiceTaskId ? '先跳过练习，继续' : '下一步' }} →</button>
      </div>
    </footer>
  </GuideDialog>

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
.tour-body { padding:30px 32px 24px; overflow:auto; min-height:0; }.tour-heading:focus { outline:none; }.tour-lead { font-size:16px; line-height:1.85; color:var(--ink-2); margin:0 0 22px; }
.welcome-note,.ready-card { display:flex; align-items:center; gap:20px; padding:22px; border:1px solid var(--line-2); border-radius:10px; background:var(--bg-sink); color:var(--amber-soft); }.welcome-note>svg,.ready-card>svg { flex:none; }.welcome-note strong,.ready-card strong { font-size:16px; color:var(--ink); }.welcome-note p,.ready-card p { color:var(--ink-2); font-size:14px; line-height:1.8; margin:6px 0 0; }
.plain-steps { list-style:decimal; padding-left:24px; margin:22px 0; font-size:15px; line-height:1.85; color:var(--ink-2); }.plain-steps li { margin:10px 0; }.soft-note { color:var(--ink-3); font-size:13px; line-height:1.85; margin:20px 0 0; }
.place-list { display:grid; gap:12px; }.place-list>div { display:flex; align-items:center; gap:18px; padding:16px 18px; border:1px solid var(--line); border-radius:10px; }.place-list svg { color:var(--amber-soft); flex:none; }.place-list p { margin:0; }.place-list strong { display:block; margin-bottom:5px; font-size:15px; }.place-list span { display:block; color:var(--ink-2); font-size:14px; line-height:1.7; }
.practice-card { display:flex; flex-direction:column; align-items:stretch; gap:12px; border:1px solid var(--line-2); border-radius:10px; padding:22px; background:var(--bg-sink); }.practice-card label { font-size:15px; font-weight:600; }.practice-card input { width:100%; min-height:48px; padding:10px 12px; background:var(--bg-raise); border:1px solid var(--line-2); border-radius:7px; font-size:16px; color:var(--ink); }.practice-card .primary-button { align-self:flex-start; }.input-note { font-size:12px; color:var(--ink-3); line-height:1.75; }.practice-success { display:flex; align-items:flex-start; gap:8px; color:var(--ink-2); font-size:14px; line-height:1.8; margin:0; }.practice-success svg { flex:none; margin-top:3px; color:var(--olive-soft,var(--amber-soft)); }.guide-error { font-size:13px; line-height:1.8; color:var(--terra); margin:0; }
.completion-example { padding:18px 22px; border:1px solid var(--line-2); border-radius:10px; background:var(--bg-sink); }.demo-label { display:block; font-size:11px; color:var(--ink-3); margin-bottom:14px; }.completion-example>div { display:flex; align-items:center; gap:12px; min-height:36px; font-size:15px; overflow-wrap:anywhere; }.demo-circle { width:24px; height:24px; flex:none; border:1px solid var(--ink-3); border-radius:50%; }.completion-example p { font-size:12px; color:var(--ink-3); padding-left:36px; margin:12px 0; }.example-done { color:var(--ink-3); }.example-done svg { flex:none; }.example-done>span { text-decoration:line-through; }.example-done small { margin-left:auto; flex:none; font-size:12px; }
.api-checklist { border:1px solid var(--line-2); border-radius:10px; padding:20px; }.api-checklist>strong { font-size:14px; }.api-checklist dl { display:grid; gap:12px; margin:16px 0 0; }.api-checklist dl>div { display:grid; grid-template-columns:100px 1fr; gap:12px; font-size:14px; line-height:1.7; }.api-checklist dt { color:var(--amber-soft); }.api-checklist dd { margin:0; color:var(--ink-2); }.choice-actions { display:flex; flex-wrap:wrap; gap:12px; margin-top:18px; }
.sample-message { border-radius:10px; border:1px solid var(--amber-border); background:var(--amber-wash); padding:18px; }.sample-message span { font-size:11px; color:var(--ink-3); }.sample-message p { font-size:15px; line-height:1.8; margin:8px 0 0; }.status-lessons { display:grid; gap:16px; margin-top:22px; }.status-lessons strong { font-size:14px; }.status-lessons p { margin:4px 0 0; font-size:14px; line-height:1.8; color:var(--ink-2); }.config-later { margin-top:8px; }
.tour-footer { flex:none; border-top:1px solid var(--line); padding:16px 24px 20px; }.tour-progress { display:flex; align-items:center; gap:14px; color:var(--ink-3); font:11px var(--mono); margin-bottom:16px; }.tour-progress>div { display:flex; flex:1; gap:5px; }.tour-progress i { flex:1; height:3px; border-radius:3px; background:var(--line-2); }.tour-progress i[data-done=true] { background:var(--amber-soft); }.tour-actions { display:flex; align-items:center; gap:10px; }.skip-button { margin-right:auto; font-size:13px; color:var(--ink-3); min-height:42px; padding:8px 0; }
.guide-save-warning { position:fixed; z-index:80; bottom:22px; left:80px; max-width:440px; display:flex; align-items:center; gap:14px; padding:16px; background:var(--bg-raise); border:1px solid var(--line-2); border-radius:10px; box-shadow:var(--shadow-panel); font-size:13px; }.guide-save-warning p { line-height:1.8; margin:0; }.guide-save-warning button { flex:none; color:var(--amber-soft); }
@media(max-width:700px) { .guide-layout { flex-direction:column; height:62dvh; max-height:none; }.guide-contents { width:auto; max-height:132px; padding:10px 12px; border-right:0; border-bottom:1px solid var(--line); display:flex; align-content:flex-start; flex-wrap:wrap; gap:4px; }.contents-label { width:100%; padding:0 4px 4px; }.guide-contents button { width:auto; padding:7px 9px; font-size:12px; }.guide-contents button span { display:none; }.guide-article { padding:22px 20px; }.offline-note { font-size:10px; }.guide-tabs { padding:10px 12px; gap:4px; }.guide-tabs button { padding:8px 12px; }.guide-footer { padding:12px 16px; }.tour-body { padding:24px 22px; }h1 { font-size:23px; }.tour-footer { padding:14px 18px; } }
@media(max-width:420px) { .tour-actions { flex-wrap:wrap; }.skip-button { order:3; width:100%; min-height:30px; text-align:center; }.tour-actions>.primary-button { flex:1; }.primary-button,.quiet-button { font-size:13px; padding:9px 12px; }.guide-footer { flex-wrap:wrap; }.guide-footer>.primary-button { flex:1; }.welcome-note,.ready-card { gap:14px; padding:16px; }.api-checklist dl>div { grid-template-columns:82px 1fr; }.tour-body { padding:22px 18px; }.practice-card { padding:16px; }.guide-save-warning { left:16px; right:16px; } }
</style>
