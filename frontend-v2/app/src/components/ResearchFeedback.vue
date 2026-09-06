<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import * as api from '../api/research'
const props = defineProps<{ project: api.Project; tasks: api.ProjectDetail['tasks']; page?: api.FeedbackPage; parentBusy: boolean }>()
const emit = defineEmits<{ updated: []; busy: [value: boolean]; prepare: [id: number] }>()
const items = ref<api.Feedback[]>([]), before = ref<number | null>(), loading = ref(false)
const note = ref(''), difficulty = ref<NonNullable<api.FeedbackInput['difficulty']>>('unspecified')
const task = ref<number | null>(null), minutes = ref<number | null>(null), key = ref(crypto.randomUUID())
const busy = ref(false), error = ref(''), notice = ref('')
const responsePlan = ref<api.ResearchPlan | null>(null)
const disabled = computed(() => busy.value || props.parentBusy)
const labels: Record<string, string> = { too_easy: '偏容易', suitable: '难度合适', too_hard: '偏困难', unspecified: '未评价难度' }
let generation = 0, alive = true
let planGeneration = 0
watch([note, difficulty, task, minutes], () => { key.value = crypto.randomUUID() }, { flush: 'sync' })
watch(() => props.page, page => { generation++; items.value = page?.items ?? []; before.value = page?.next_before; loading.value = false }, { immediate: true })
onUnmounted(() => { alive = false; generation++; planGeneration++ })
async function showPlan(id: number) {
  const g = ++planGeneration; error.value = ''; responsePlan.value = null
  try {
    const plan = await api.readPlan(id)
    if (alive && g === planGeneration && plan.project_id === props.project.id) responsePlan.value = plan
  } catch (e) { if (alive && g === planGeneration) error.value = e instanceof Error ? e.message : String(e) }
}
async function more() {
  if (!before.value || loading.value) return
  const g = ++generation; loading.value = true; error.value = ''
  try {
    const page = await api.listFeedback(props.project.id, before.value)
    if (!alive || g !== generation) return
    items.value = [...items.value, ...page.items]; before.value = page.next_before
  } catch (e) { if (alive && g === generation) error.value = e instanceof Error ? e.message : String(e) }
  finally { if (alive && g === generation) loading.value = false }
}
async function act(fn: () => Promise<void>) {
  if (disabled.value) return
  busy.value = true; emit('busy', true); error.value = ''; notice.value = ''
  try { await fn() } catch (e) { if (alive) error.value = e instanceof Error ? e.message : String(e) }
  finally { if (alive) { busy.value = false; emit('busy', false); emit('updated') } }
}
async function save() {
  await act(async () => {
    await api.recordFeedback(props.project, { note: note.value, difficulty: difficulty.value, task_link_id: task.value, actual_minutes: minutes.value === null || String(minutes.value) === '' ? null : minutes.value }, key.value)
    if (!alive) return
    note.value = ''; difficulty.value = 'unspecified'; minutes.value = null; task.value = null; key.value = crypto.randomUUID()
    notice.value = '反馈已保存。可以据此补充练习或继续下一阶段。'
  })
}
async function withdraw(id: number) {
  await act(async () => { await api.withdrawFeedback(props.project, id); if (alive) notice.value = '反馈已撤回；已落实的任务保留，相关旧预览需重新生成。' })
}
</script>

<template>
  <article class="learning-feedback" aria-label="学习反馈">
    <h2>学习反馈</h2><p class="hint">记下收获、卡住的地方和实际投入，让后续计划更适合你。这里保留你的自述。</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <form v-if="project.status === 'active'" @submit.prevent="save">
      <label>这次学到了什么，或哪里需要帮助<textarea v-model="note" required maxlength="4000" rows="3" :disabled="disabled" placeholder="例如：能运行示例，但还不理解为什么要这样做，希望多一些具体练习。"></textarea></label>
      <div class="fields"><label>关联任务<select v-model="task" :disabled="disabled"><option :value="null">整个项目</option><option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.title }}</option></select></label>
        <label>难度感受<select v-model="difficulty" :disabled="disabled"><option v-for="(label, value) in labels" :key="value" :value="value">{{ label }}</option></select></label>
        <label>实际投入（分钟，可选）<input v-model.number="minutes" type="number" min="0" max="10080" :disabled="disabled" placeholder="未记录"></label></div>
      <button class="primary" :disabled="disabled || !note.trim()">{{ busy ? '保存中…' : '保存反馈' }}</button>
    </form>
    <p v-if="!items.length" class="hint">还没有反馈。即使任务已完成，也可以记下仍需巩固的内容。</p>
    <div v-for="item in items" :key="item.id" class="entry">
      <div class="meta">{{ item.created_at.replace('T', ' ').slice(0, 16) }} · {{ labels[item.difficulty || 'unspecified'] }}<span v-if="item.actual_minutes != null"> · 实际 {{ item.actual_minutes }} 分钟</span></div>
      <p v-if="item.task_link_id" class="hint">{{ tasks.find(t => t.id === item.task_link_id)?.title || '关联任务记录' }}</p>
      <p class="prose">{{ item.note }}</p><p v-if="item.applied_plan_ids?.length" class="hint">已有 {{ item.applied_plan_ids.length }} 个落实方案回应这条反馈。学习效果可继续记录。</p>
      <div class="actions"><button v-for="id in item.applied_plan_ids" :key="id" @click="showPlan(id)">查看回应方案 #{{ id }}</button></div>
      <div v-if="project.status === 'active'" class="actions"><button v-if="tasks.length" :disabled="disabled" @click="emit('prepare', item.id)">据此调整学习内容</button><button :disabled="disabled" @click="withdraw(item.id)">撤回反馈</button></div>
    </div>
    <button v-if="before" @click="more" :disabled="loading || disabled">{{ loading ? '读取中…' : '查看更早反馈' }}</button>
    <section v-if="responsePlan" class="response-plan" aria-label="回应方案"><h3>回应方案 #{{ responsePlan.id }}</h3><p class="prose">{{ responsePlan.rationale }}</p><ol><li v-for="(unit,i) in responsePlan.units" :key="i"><strong>{{ unit.title }}</strong><p class="prose">{{ unit.outcome }}</p></li></ol><button @click="planGeneration++; responsePlan = null">收起方案</button></section>
  </article>
</template>

<style scoped>
.learning-feedback { border:1px solid var(--line); border-radius:14px; padding:20px; margin:18px 0; background:var(--bg-raise); }
h2 { font-size:18px; margin:0 0 12px; }.hint,.meta { color:var(--ink-3); font-size:13px; line-height:1.6; }.fields { display:flex; gap:12px; flex-wrap:wrap; margin:12px 0; }.fields label { flex:1; min-width:150px; }
label { display:flex; flex-direction:column; gap:6px; font-size:13px; }textarea,input,select { width:100%; box-sizing:border-box; font:inherit; padding:9px; border:1px solid var(--line); border-radius:8px; color:var(--ink); background:var(--bg-app); }select { max-width:100%; }button { padding:8px 12px; border:1px solid var(--line); border-radius:8px; color:var(--ink); background:var(--bg-raise); cursor:pointer; }button:disabled { opacity:.5; cursor:default; }.primary { background:var(--btn-new-bg); color:var(--btn-new-text); }.entry { border-top:1px solid var(--line); padding:16px 0; margin-top:14px; }.prose { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.7; }.actions { display:flex; flex-wrap:wrap; gap:8px; }.error { color:var(--terra); }.notice { color:var(--amber); }.response-plan { border:1px solid var(--amber-border); border-radius:8px; padding:14px; margin-top:14px; }
</style>
