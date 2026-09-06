<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ResearchProjectForm from '../components/ResearchProjectForm.vue'
import MaterialSearch from '../components/MaterialSearch.vue'
import { materialTarget } from '../api/materials'
import ResearchWatch from '../components/ResearchWatch.vue'
import ResearchFollowups from '../components/ResearchFollowups.vue'
import ResearchFeedback from '../components/ResearchFeedback.vue'
import ResearchPlanHistory from '../components/ResearchPlanHistory.vue'
import * as api from '../api/research'
import { listFiles, uploadFile, type LibraryFile } from '../api/files'
import { updateTask } from '../api/tasks'
import { useRunStore } from '../stores/run'
import { useResearchContext } from '../stores/researchContext'
const route = useRoute(), router = useRouter(), run = useRunStore(), context = useResearchContext()
const projects = ref<api.Project[]>([]), detail = ref<api.ProjectDetail | null>(null)
const archived = ref(false), busy = ref(false), loading = ref(false), error = ref(''), notice = ref('')
const form = ref<'new' | 'edit' | null>(null), editVersion = ref(0), editSpec = ref<api.ProjectSpec>()
const token = ref(crypto.randomUUID()), sourceUrl = ref(''), fileId = ref<number | null>(null), files = ref<LibraryFile[]>([])
const editor = ref(false), rationale = ref(''), steps = ref<api.Step[]>([])
const feedbackIds = ref<number[]>([])
const planEditor = ref<HTMLFormElement>()
const editorMode = ref<'extension' | 'insert_before' | 'replace'>('extension')
const targetLinkId = ref<number | null>(null), manualMoveIds = ref<number[]>([])
const selected = computed(() => { const n = Number(route.query.project); return Number.isSafeInteger(n) && n > 0 ? n : null })
const project = computed(() => detail.value?.project), plan = computed(() => detail.value?.latest_plan)
const active = computed(() => project.value?.status === 'active')
const readySources = computed(() => detail.value?.sources.filter(s => s.status === 'verified' && !s.superseded_by) ?? [])
const revisionTargets = computed(() => detail.value?.revision_targets ?? [])
const editableTargets = computed(() => revisionTargets.value.filter(t => editorMode.value === 'replace' ? t.can_replace : t.can_insert_before))
const manualTargets = computed(() => revisionTargets.value.filter(t => t.can_move && t.manual_schedule))
const targetTask = computed(() => detail.value?.tasks.find(t => t.id === targetLinkId.value))
const manualTargetPermission = computed(() => editorMode.value === 'replace' && manualTargets.value.some(t => t.task_link_id === targetLinkId.value) && !manualMoveIds.value.includes(targetLinkId.value!))
let generation = 0
function message(e: unknown) { return e instanceof Error ? e.message : String(e) }
async function load() {
  const g = ++generation, id = selected.value
  loading.value = true
  try {
    const [list, data] = await Promise.all([api.listProjects(archived.value), id ? api.readProject(id) : Promise.resolve(null)])
    if (g !== generation) return
    projects.value = list; detail.value = data
    context.project = data ? { id: data.project.id, title: data.project.spec.title } : null
  } catch (e) { if (g === generation) error.value = message(e) }
  finally { if (g === generation) loading.value = false }
}
async function act(fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  const id = selected.value
  try { await fn() } catch (e) { if (id === selected.value) error.value = message(e) }
  finally { busy.value = false; await load() }
}
function choose(id: number) { void router.replace({ name: 'research', query: { project: id } }) }
function openForm(kind: 'new' | 'edit') {
  form.value = kind; token.value = crypto.randomUUID(); error.value = ''
  editSpec.value = kind === 'edit' && project.value ? JSON.parse(JSON.stringify(project.value.spec)) : undefined
  editVersion.value = project.value?.version ?? 0
}
async function save(spec: api.ProjectSpec) {
  const id = selected.value, kind = form.value
  await act(async () => {
    const saved = kind === 'edit' && id ? await api.updateProject(id, editVersion.value, spec) : await api.createProject(spec, token.value)
    form.value = null; archived.value = false; await router.replace({ name: 'research', query: { project: saved.id } })
    notice.value = kind === 'edit' ? '目标与约束已保存。已有安排可在下方预览重排。' : '项目已建立。可在左侧让知时查找资料并拟定学习计划。'
  })
}
function addStep() { steps.value.push({ title: '', outcome: '', minutes: 45, source_ids: [] }) }
function openEditor() { if (!steps.value.length) addStep(); editor.value = true; void nextTick(() => planEditor.value?.scrollIntoView({ block: 'start', behavior: 'smooth' })) }
function startExtension() { editorMode.value = 'extension'; openEditor() }
function startRevision(mode: 'insert_before' | 'replace', id: number) { editorMode.value = mode; targetLinkId.value = id; openEditor() }
function fromFeedback(id: number) { feedbackIds.value = [...new Set([...feedbackIds.value, id])]; openEditor() }
async function preview() {
  const p = project.value; if (!p) return
  await act(async () => {
    if (p.total_tasks && editorMode.value !== 'extension') {
      if (!targetLinkId.value) throw new Error('请先选择要插入或替换的任务。')
      await api.previewRevision(p.id, { version: p.version, mode: editorMode.value, target_link_id: targetLinkId.value,
        rationale: rationale.value, steps: steps.value, feedback_ids: feedbackIds.value, movable_task_link_ids: manualMoveIds.value })
    } else if (p.total_tasks) await api.previewExtension(p.id, p.version, rationale.value, steps.value, feedbackIds.value)
    else await api.previewPlan(p.id, p.version, rationale.value, steps.value)
    editor.value = false; steps.value = []; rationale.value = ''; feedbackIds.value = []
    editorMode.value = 'extension'; targetLinkId.value = null; manualMoveIds.value = []
    notice.value = '预览已保存，核对后即可加入日历。'
  })
}
async function gather() {
  const id = selected.value; if (!id) return
  await act(async () => {
    const result = await api.gatherSources(id)
    if (id !== selected.value) return
    notice.value = `本次获取 ${result.sources.filter(s => s.status === 'verified').length} 份正文。可在下方阅读，使用前请核对内容是否适合你的目标。`
    if (result.errors.length) error.value = result.errors.map(e => Object.values(e).join('：')).join('\n')
  })
}
async function sourceAction(fn: (id: number) => Promise<api.ResearchSource>) {
  const id = selected.value; if (!id) return
  await act(async () => {
    const source = await fn(id)
    if (id !== selected.value) return
    if (source.status !== 'verified' || source.error) throw new Error(source.error || '暂未取得正文，可稍后重试。')
    sourceUrl.value = ''; fileId.value = null; notice.value = '资料正文已关联到项目。'
  })
}
async function pickUpload(e: Event) {
  const el = e.target as HTMLInputElement, file = el.files?.[0]; el.value = ''
  if (file) await sourceAction(async id => { const saved = await uploadFile(file); return api.attachMaterial(id, saved.id) })
}
async function loadFiles() {
  await act(async () => { files.value = (await listFiles()).filter(f => f.resource_type !== 'link'); if (!files.value.length) notice.value = '资料库中暂时没有可关联的文件，可以先上传学习材料。' })
}
async function apply() {
  const p = plan.value; if (!p) return
  await act(async () => { await api.applyPlan(p.id); window.dispatchEvent(new Event('zhishi:tasks-changed')); notice.value = '计划已落实。已安排的时段可在日历查看，未排入的事项保留在看板。' })
}
async function movePlan() {
  const p = project.value; if (!p) return
  await act(async () => { await api.replan(p); notice.value = '重排预览已保存；完成、进行中和手动调整的安排会保留。' })
}
async function archive() {
  const p = project.value; if (!p) return
  await act(async () => { const saved = await api.archiveProject(p); archived.value = saved.status === 'archived'; notice.value = '项目状态已更新，已有任务与日历安排保留。' })
}
async function complete(id: number) {
  await act(async () => { await updateTask(id, { status: 'done' }); window.dispatchEvent(new Event('zhishi:tasks-changed')); notice.value = '已记录完成，项目进度已更新。' })
}
function slot(index: number) { return plan.value?.assignments.find(a => a.unit_index === index) }
function unassigned(index: number) { return plan.value?.unassigned.find(a => a.unit_index === index)?.reason }
function sourceNames(ids: number[]) { return ids.map(id => detail.value?.sources.find(s => s.id === id)?.title ?? '资料已不可用').join('、') }
function outcomeText(value: string) {
  if (!value.startsWith('完成标准：')) return value
  return value.slice('完成标准：'.length).split('\n\n学习资料：')[0].split('\n\n本步骤未关联')[0]
}
const statusNames: Record<string, string> = { todo: '待开始', doing: '进行中', done: '已完成', deleted: '已删除', missing: '记录已移除' }
watch(editorMode, () => { targetLinkId.value = null; manualMoveIds.value = [] }, { flush: 'sync' })
watch(selected, () => { generation++; detail.value = null; context.project = null; form.value = null; editor.value = false; steps.value = []; feedbackIds.value = []; editorMode.value = 'extension'; targetLinkId.value = null; manualMoveIds.value = []; rationale.value = ''; error.value = ''; notice.value = ''; void load() })
watch(archived, () => { void load() })
watch(() => run.phase, phase => { if (['completed','cancelled','awaiting_approval'].includes(phase)) void load() })
onMounted(() => { void load(); window.addEventListener('focus', load) })
onUnmounted(() => { generation++; context.project = null; window.removeEventListener('focus', load) })
</script>

<template>
  <section class="research-view" aria-label="学习与研究">
    <header><div><p class="eyebrow">从一个想法，到持续的进展</p><h1>学习与研究</h1><p class="hint">告诉左侧的知时你想学什么。资料、计划和每一次进步，都在这里汇集。</p></div><button @click="openForm('new')" :disabled="busy">＋ 新建项目</button></header>
    <div class="tabs"><button :class="{ chosen: !archived }" @click="archived = false" :disabled="busy">进行中的项目</button><button :class="{ chosen: archived }" @click="archived = true" :disabled="busy">已归档</button><button @click="error = ''; load()" :disabled="loading">{{ loading ? '读取中…' : '刷新' }}</button></div>
    <div v-if="error" class="error" role="alert">{{ error }}</div><div v-if="notice" class="notice" role="status">{{ notice }}</div>
    <ResearchProjectForm v-if="form" :key="`${form}-${token}`" :initial="editSpec" :busy="busy" @save="save" @cancel="form = null" />
    <nav class="project-list" aria-label="项目列表"><button v-for="p in projects" :key="p.id" :class="{ chosen: selected === p.id }" :disabled="busy" @click="choose(p.id)"><strong>{{ p.spec.title }}</strong><span>{{ p.completed_tasks }} / {{ p.total_tasks }} 已完成 · {{ p.verified_sources }} 份资料</span></button></nav>
    <p v-if="!loading && !projects.length" class="empty">{{ archived ? '暂时没有归档项目。' : '从你一直想学的一件事开始。新建项目，或直接把想法告诉知时。' }}</p>
    <template v-if="detail && project">
      <article class="overview"><div class="row-head"><h2>{{ project.spec.title }}</h2><span class="badge">{{ active ? '进行中' : '已归档' }}</span></div><p class="prose">{{ project.spec.objective }}</p><p v-if="project.spec.background" class="hint prose">现有基础与约束：{{ project.spec.background }}</p>
        <div class="stats"><strong>{{ project.completed_tasks }}<small> / {{ project.total_tasks }} 已完成</small></strong><strong>{{ project.verified_sources }}<small> 份资料正文</small></strong><strong>{{ project.spec.daily_minutes }}<small> 分钟 / 天</small></strong></div>
        <progress :value="project.completed_tasks" :max="Math.max(1, project.total_tasks)" aria-label="项目完成进度"></progress>
        <p class="hint">规划窗口：{{ project.spec.start_date }} 起{{ project.spec.end_date ? `，至 ${project.spec.end_date}` : '的两周' }} · {{ project.spec.window_start ? `${project.spec.window_start}–${project.spec.window_end}` : '采用设置中的工作时段' }}</p>
        <p v-for="assumption in project.assumptions" :key="assumption" class="hint">{{ assumption }}</p>
        <p v-if="project.missing_tasks" class="hint">有 {{ project.missing_tasks }} 项任务已删除或移除，重排不会重新创建。</p>
        <div class="actions"><button v-if="active" @click="openForm('edit')" :disabled="busy">调整目标与时间</button><button @click="archive" :disabled="busy">{{ active ? '归档项目' : '恢复项目' }}</button></div>
      </article>
      <ResearchWatch :key="`watch-${project.id}`" :project-id="project.id" :parent-busy="busy" @updated="load" />
      <ResearchFollowups :key="project.id" :project-id="project.id" :parent-busy="busy" @updated="load" />
      <ResearchFeedback :key="`feedback-${project.id}`" :project="project" :tasks="detail.tasks" :page="detail.feedback" :parent-busy="busy" @busy="busy = $event" @updated="load" @prepare="fromFeedback" />
      <article><div class="row-head"><h2>项目资料</h2><button v-if="active" class="primary" @click="gather" :disabled="busy">{{ busy ? '处理中…' : '检索资料' }}</button></div><p class="hint">检索使用项目主题作为关键词。获取到正文的网页会保存至资料库；“已获取”表示可以阅读，不代表内容已证实。</p>
        <template v-if="active"><form class="inline-form" @submit.prevent="sourceAction(id => api.addSource(id, sourceUrl))"><label>添加资料链接<input v-model="sourceUrl" type="url" required placeholder="https://…"></label><button :disabled="busy">获取正文</button></form>
          <div class="actions"><label class="upload">上传学习材料<input type="file" :disabled="busy" @change="pickUpload"></label><button @click="loadFiles" :disabled="busy">从资料库选择</button></div>
          <form v-if="files.length" class="inline-form" @submit.prevent="sourceAction(id => api.attachMaterial(id, fileId!))"><label>已有材料<select v-model="fileId" required><option :value="null" disabled>选择材料</option><option v-for="f in files" :key="f.id" :value="f.id">{{ f.original_name }}</option></select></label><button :disabled="busy || !fileId">关联项目</button></form>
        </template>
        <MaterialSearch v-if="detail.sources.length" :project-id="project.id" />
        <p v-if="!detail.sources.length" class="empty">资料可以来自公开网页，也可以是你自己的文件。</p>
        <div v-for="s in detail.sources" :key="s.id" class="source"><div class="row-head"><h3>{{ s.title }}</h3><span class="badge">{{ s.superseded_by ? '历史版本' : s.status === 'verified' ? '已获取正文' : s.status === 'failed' ? '获取失败' : '待获取' }}</span></div>
          <a v-if="s.kind === 'web' && api.publicSourceUrl(s.url)" :href="api.publicSourceUrl(s.url)" target="_blank" rel="noopener noreferrer">打开原网页 ↗</a><RouterLink v-else to="/library">打开资料库 →</RouterLink>
          <p v-if="s.retrieved_at" class="hint">获取于 {{ s.retrieved_at.replace("T", " ").slice(0, 19) }}</p><p v-if="s.superseded_by" class="hint">已获取更新版本；此版本保留供核对原任务引用。</p><p v-if="s.error" class="error">{{ s.error }}</p><p v-if="s.library_state !== 'active'" class="hint">原资料库记录已删除或不可用，项目保留已有正文。</p>
          <p v-if="s.library_file_id && s.library_state === 'active'"><RouterLink :to="materialTarget(s.library_file_id)">分段阅读与正文检索 →</RouterLink><span v-if="s.document" class="hint"> · {{ s.document.total_parts }} 个片段{{ s.document.partial ? '，保存范围有限或完整性未确认' : '' }}</span></p>
          <p v-for="warning in (s.document?.warnings || [])" :key="warning" class="hint">{{ warning }}</p><p v-if="s.kind === 'web' && s.status === 'verified' && !s.document && !s.superseded_by" class="hint">旧版网页只保存开头预览，重新获取后可继续阅读后续内容。</p><details v-if="s.content"><summary>阅读开头预览</summary><pre>{{ s.content }}</pre></details><button v-if="active && !s.superseded_by && s.kind === 'web'" :data-refresh-source="s.id" @click="sourceAction(id => api.fetchSource(id, s.id, s.status === 'verified'))" :disabled="busy">{{ s.status === 'verified' ? '重新获取网页' : '重试获取' }}</button>
        </div>
      </article>
      <article><div class="row-head"><h2>{{ project.total_tasks ? '计划与重排' : '学习计划' }}</h2><button v-if="active && project.total_tasks" @click="movePlan" :disabled="busy">预览重排</button><button v-if="active" @click="startExtension" :disabled="busy">{{ project.total_tasks ? "拟定学习内容" : "手动拟定步骤" }}</button></div>
        <p class="hint">{{ project.total_tasks ? '可在未开始的任务前补充基础、替换已有内容，或追加下一阶段。课程顺序与调整历史都会保留。' : '在左侧说“结合这些资料制定学习计划”，知时会拟定内容，程序按真实日历安排时间。也可以自己填写步骤。' }}</p>
        <form v-if="editor" ref="planEditor" class="plan-editor" @submit.prevent="preview"><template v-if="project.total_tasks">
            <label>本次如何调整<select v-model="editorMode" :disabled="busy"><option value="extension">追加后续阶段</option><option value="insert_before">在已有任务前插入</option><option value="replace">替换尚未开始的内容</option></select></label>
            <template v-if="editorMode !== 'extension'"><label>选择目标任务<select v-model="targetLinkId" required :disabled="busy"><option :value="null" disabled>选择尚未开始的任务</option><option v-for="t in editableTargets" :key="t.task_link_id" :value="t.task_link_id">{{ t.title }}</option></select></label>
              <p v-if="!editableTargets.length" class="hint">当前没有适合此操作的任务。完成项和已有学习记录的内容保留；有子任务的内容可选择前插补充。</p>
              <details v-if="targetTask"><summary>查看目标当前内容：{{ targetTask.title }}</summary><pre>{{ targetTask.notes }}</pre></details>
              <p class="hint">{{ editorMode === 'replace' ? '替换会更新目标任务的标题、完成标准和预计时长；原笔记保存在方案历史，原任务编号及附件保留。' : '新内容放在目标任务之前，后续重排仍沿用这个顺序。' }}</p>
              <fieldset v-if="manualTargets.length" class="manual-options"><legend>手工时间默认保留</legend><p class="hint">如果同意本次移动某个手工安排，请勾选对应任务。</p><label v-for="t in manualTargets" :key="t.task_link_id" class="check"><input v-model="manualMoveIds" type="checkbox" :value="t.task_link_id" :disabled="busy">{{ t.title }}</label></fieldset>
              <p v-if="manualTargetPermission" class="hint">目标有手工安排。替换需要重新安排时间，请先明确是否允许移动。</p>
            </template>
            <p v-else class="hint">新内容接在已有未完成安排之后。需要延长规划窗口时，先调整上面的时间。</p>
          </template><p v-if="feedbackIds.length" class="hint">回应反馈：{{ feedbackIds.map(id => `#${id}`).join("、") }} <button type="button" @click="feedbackIds = []" :disabled="busy">清除关联</button></p><label>为什么按这个顺序学习<textarea v-model="rationale" required maxlength="4000" rows="2"></textarea></label>
          <fieldset v-for="(step,i) in steps" :key="i"><legend>步骤 {{ i + 1 }}</legend><label>要做什么<input v-model="step.title" required maxlength="160"></label><label>完成标准<textarea v-model="step.outcome" required maxlength="3000" rows="2"></textarea></label><label>预计总投入（分钟）<input v-model.number="step.minutes" required type="number" min="15" max="960"></label><p class="hint">引用资料（可选；没有资料依据时请在说明中写明）</p><label v-for="s in readySources" :key="s.id" class="check"><input v-model="step.source_ids" type="checkbox" :value="s.id">{{ s.title }}</label><button type="button" @click="steps.splice(i, 1)" :disabled="steps.length === 1 || busy">移除此步骤</button></fieldset>
          <div class="actions"><button type="button" @click="addStep" :disabled="steps.length >= 40 || busy">＋ 下一步</button><button type="button" @click="editor = false" :disabled="busy">收起</button><button class="primary" :disabled="busy || manualTargetPermission || (project.total_tasks > 0 && editorMode !== 'extension' && !targetLinkId)">预览时间安排</button></div>
        </form>
        <div v-if="plan" class="plan"><p class="badge">{{ plan.kind === 'replan' ? '重排方案' : plan.kind === 'extension' ? '追加学习方案' : plan.kind === 'revision' ? '课程调整方案' : '学习方案' }} · {{ plan.state === 'applied' ? '已落实' : '待落实' }}</p><p class="prose">{{ plan.rationale }}</p>
          <div v-if="plan.revision" class="revision-summary"><p><strong>{{ plan.revision.mode === 'replace' ? '替换内容' : '前插内容' }}</strong> · 目标：{{ plan.revision.before_task.title }}</p><p class="hint">新增 {{ plan.units.filter(u => !u.existing_task_id).length }} 项 · 替换 {{ plan.units.filter(u => u.replace_content).length }} 项；已有任务的编号和完成记录保留。</p><details><summary>修改前记录</summary><pre>{{ plan.revision.before_task.notes }}</pre></details><p v-for="t in plan.revision.moved_manual" :key="String(t.task_link_id)" class="hint">本次明确允许调整手工时间：{{ t.title }}</p><p v-for="warning in plan.revision.warnings" :key="warning" class="error">{{ warning }}</p></div><p class="hint">{{ plan.assignments.length }} 项排入日历 · {{ plan.unassigned.length }} 项未排入 · {{ plan.preserved.length }} 项保留</p>
          <p v-if="plan.state === 'draft' && plan.project_version !== project.version" class="error">项目或反馈已修改，请重新生成预览。</p>
          <ol><li v-for="(unit,i) in plan.units" :key="i"><strong>{{ unit.title }}</strong><span v-if="plan.revision" class="badge">{{ unit.replace_content ? '替换原步骤' : unit.existing_task_id ? '重排已有任务' : '新内容' }}</span><p class="prose">{{ outcomeText(unit.outcome) }}</p><p class="time">{{ unit.minutes }} 分钟 · {{ slot(i) ? `${slot(i)!.date} ${slot(i)!.start}–${slot(i)!.end}` : `暂未安排：${unassigned(i) || '保留现状'}` }}</p><p v-if="unit.source_ids.length" class="hint">依据：{{ sourceNames(unit.source_ids) }}</p><blockquote v-for="(ref,r) in (unit.source_refs || [])" :key="r"><p>{{ ref.quote }}</p><RouterLink v-if="detail.sources.find(s => s.id === ref.source_id)?.library_file_id" :to="materialTarget(detail.sources.find(s => s.id === ref.source_id)!.library_file_id!, ref.part, ref.revision)">核对原文 · 片段 {{ ref.part }}</RouterLink></blockquote></li></ol>
          <p v-if="plan.preserved.length" class="hint">已完成、进行中、手工调整或已删除的任务保持现状。下方显示任务的实时状态。</p>
          <p v-if="plan.unassigned.length" class="hint">未排入的事项会保留为待办。可以扩大规划窗口或可用时间后再重排。</p>
          <div class="actions"><RouterLink v-if="plan.state === 'applied'" to="/calendar">查看日历 →</RouterLink><button v-if="active && plan.state === 'draft'" class="primary" @click="apply" :disabled="busy || plan.project_version !== project.version">确认落实计划</button></div>
        </div><p v-else class="empty">目标清楚之后，把第一步安排下来。</p>
      </article>
      <article v-if="detail.tasks.length"><div class="row-head"><h2>实际进度</h2><RouterLink to="/board">打开看板 →</RouterLink></div><div v-for="task in detail.tasks" :key="task.id" class="task"><div class="row-head"><h3>{{ task.title }}</h3><span class="badge">{{ statusNames[task.status] || task.status }}</span></div><p v-for="s in task.slots" :key="s.id" class="hint">{{ s.date }} {{ s.start || '' }}{{ s.end ? `–${s.end}` : '' }}</p><details v-if="task.notes"><summary>完成标准与记录</summary><pre>{{ outcomeText(task.notes) }}</pre></details><blockquote v-for="(ref,r) in (task.source_refs || [])" :key="r"><p>{{ ref.quote }}</p><RouterLink v-if="detail.sources.find(s => s.id === ref.source_id)?.library_file_id" :to="materialTarget(detail.sources.find(s => s.id === ref.source_id)!.library_file_id!, ref.part, ref.revision)">核对原文 · 片段 {{ ref.part }}</RouterLink></blockquote><div v-if="active" class="actions"><button v-if="revisionTargets.find(t => t.task_link_id === task.id)?.can_insert_before" @click="startRevision('insert_before', task.id)" :disabled="busy">在此之前补充</button><button v-if="revisionTargets.find(t => t.task_link_id === task.id)?.can_replace" @click="startRevision('replace', task.id)" :disabled="busy">调整这一步内容</button></div><button v-if="active && task.task_id && ['todo','doing'].includes(task.status)" @click="complete(task.task_id)" :disabled="busy">标记完成</button></div></article>
      <ResearchPlanHistory :key="`history-${project.id}`" :project-id="project.id" :version="project.version" />
    </template>
  </section>
</template>

<style scoped>
.revision-summary { border:1px solid var(--amber-border); border-radius:8px; padding:12px; margin:12px 0; }.revision-summary p { line-height:1.7; }.research-view { padding:24px; max-width:1060px; width:100%; margin:auto; color:var(--ink); }
header,.row-head,.actions,.tabs,.inline-form { display:flex; align-items:center; gap:12px; justify-content:space-between; flex-wrap:wrap; } header { align-items:flex-start; }
h1 { font:28px var(--serif); margin:0; }h2 { font-size:17px; margin:0; }h3 { font-size:14px; margin:0; overflow-wrap:anywhere; }.eyebrow,.hint,:deep(.hint) { font-size:12px; color:var(--ink-3); line-height:1.8; }.eyebrow { margin:0 0 7px; }
.tabs { justify-content:flex-start; margin:18px 0; }.project-list { display:flex; gap:8px; overflow-x:auto; padding-bottom:12px; }.project-list button { min-width:180px; max-width:260px; text-align:left; white-space:normal; flex-shrink:0; }.project-list strong,.project-list span { display:block; overflow-wrap:anywhere; }.project-list span { margin-top:8px; color:var(--ink-3); font-size:11px; }
article,:deep(.project-form) { border:1px solid var(--line); border-radius:12px; padding:20px; margin:14px 0; background:var(--bg-raise); }.row-head { margin-bottom:12px; }.prose { white-space:pre-wrap; line-height:1.8; font-size:13px; overflow-wrap:anywhere; }.stats { display:flex; gap:24px; flex-wrap:wrap; margin:20px 0 10px; }.stats strong { font-size:24px; font-weight:500; }.stats small { font-size:12px; color:var(--ink-3); }progress { width:100%; height:6px; accent-color:var(--amber); }
:deep(button),:deep(input),:deep(select),:deep(textarea) { font:inherit; color:var(--ink); }:deep(button) { font-size:12px; border:1px solid var(--line); border-radius:7px; background:var(--bg-raise); padding:8px 11px; cursor:pointer; }:deep(button:disabled) { opacity:.5; cursor:default; }:deep(button:hover) { border-color:var(--ink-3); }:deep(.primary) { color:var(--btn-ok-text); background:var(--amber); border-color:transparent; font-weight:600; }.chosen { border-color:var(--amber); color:var(--amber); }
:deep(label) { display:flex; flex-direction:column; gap:6px; font-size:12px; color:var(--ink-3); }:deep(input:not([type=checkbox])),:deep(select),:deep(textarea) { width:100%; min-width:0; padding:10px; border:1px solid var(--line); border-radius:7px; background:var(--bg); box-sizing:border-box; }:deep(input[type=checkbox]) { accent-color:var(--amber); }:deep(.check) { flex-direction:row; align-items:center; margin:8px 0; }:deep(.pair) { display:grid; grid-template-columns:1fr 1fr; gap:12px; }:deep(fieldset) { border:1px solid var(--line); border-radius:8px; padding:12px; margin:10px 0; min-width:0; }:deep(legend) { font-size:12px; color:var(--ink-3); }:deep(.project-form) { display:grid; gap:12px; }.plan-editor { display:grid; gap:12px; }.plan-editor fieldset label { margin-bottom:12px; }
.inline-form { align-items:flex-end; margin:16px 0; }.inline-form label { flex:1; min-width:180px; }.actions { justify-content:flex-end; margin-top:12px; }.upload { border:1px solid var(--line); border-radius:7px; padding:8px; }.upload input { max-width:220px; font-size:12px; }.source,.task { border-top:1px solid var(--line); margin-top:16px; padding-top:16px; }.badge { border:1px solid var(--line); border-radius:5px; padding:3px 7px; font-size:11px; color:var(--amber); }.empty { text-align:center; color:var(--ink-3); padding:24px 8px; font-size:13px; line-height:1.8; }
a { color:var(--amber); font-size:12px; }details { margin:12px 0; }summary { cursor:pointer; font-size:12px; color:var(--ink-3); }pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:320px; overflow:auto; font-family:inherit; font-size:12px; line-height:1.8; background:var(--bg); padding:12px; border-radius:6px; }.error,.notice { padding:12px; border:1px solid var(--line); border-radius:8px; font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.8; margin:12px 0; }.error { color:var(--terra); }.notice,.time { color:var(--amber); }.plan ol { padding-left:22px; }.plan li { padding:12px 0; border-bottom:1px solid var(--line); font-size:13px; line-height:1.8; overflow-wrap:anywhere; }.plan li p { margin:6px 0; }
:deep(button:focus-visible),:deep(input:focus-visible),:deep(select:focus-visible),:deep(textarea:focus-visible),a:focus-visible,summary:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }
@media(max-width:700px) { .research-view { padding:16px; }article,:deep(.project-form) { padding:14px; }:deep(.pair) { grid-template-columns:1fr; }.stats { gap:14px; } }
</style>
