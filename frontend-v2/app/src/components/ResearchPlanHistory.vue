<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import * as api from '../api/research'
const props = defineProps<{ projectId: number; version: number }>()
const items = ref<api.PlanHistory['items']>([]), before = ref<number | null>(), selected = ref<api.ResearchPlan | null>(null)
const busy = ref(false), error = ref('')
const kinds: Record<string, string> = { initial: '初始方案', replan: '时间重排', extension: '后续阶段', revision: '课程调整' }
let generation = 0, detailGeneration = 0, alive = true
async function load(more = false) {
  const g = ++generation, pid = props.projectId
  busy.value = true; error.value = ''
  try {
    const page = await api.listPlans(pid, more ? before.value : null)
    if (!alive || g !== generation) return
    items.value = more ? [...items.value, ...page.items] : page.items; before.value = page.next_before
  } catch (e) { if (alive && g === generation) error.value = e instanceof Error ? e.message : String(e) }
  finally { if (alive && g === generation) busy.value = false }
}
async function show(id: number) {
  const g = ++detailGeneration, pid = props.projectId
  error.value = ''; selected.value = null
  try {
    const plan = await api.readPlan(id)
    if (alive && g === detailGeneration && pid === props.projectId && plan.project_id === pid) selected.value = plan
  } catch (e) { if (alive && g === detailGeneration) error.value = e instanceof Error ? e.message : String(e) }
}
watch(() => [props.projectId, props.version], () => { generation++; detailGeneration++; selected.value = null; items.value = []; void load() }, { immediate: true })
onUnmounted(() => { alive = false; generation++; detailGeneration++ })
</script>

<template>
  <article class="plan-history" aria-label="方案历史"><h2>方案历史</h2><p class="hint">回看已经落实的内容和调整理由。这里展示当时的方案，当前进度以上面的任务为准。</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="!items.length && !busy" class="hint">还没有落实的方案。</p>
    <div class="history-list"><button v-for="item in items" :key="item.id" @click="show(item.id)"><strong>{{ kinds[item.kind] || item.kind }} #{{ item.id }}</strong><span>{{ (item.applied_at || item.created_at).replace('T',' ').slice(0,16) }}</span></button></div>
    <button v-if="before" :disabled="busy" @click="load(true)">{{ busy ? '读取中…' : '查看更早方案' }}</button>
    <section v-if="selected" class="history-detail"><h3>{{ kinds[selected.kind] || selected.kind }} #{{ selected.id }}</h3><p class="prose">{{ selected.rationale }}</p>
      <div v-if="selected.revision" class="before-content"><h4>{{ selected.revision.mode === 'replace' ? '替换前的内容' : '插入位置原有内容' }}：{{ selected.revision.before_task.title }}</h4><pre>{{ selected.revision.before_task.notes }}</pre><p class="hint">原预计 {{ selected.revision.before_task.minutes || '未填写' }} 分钟 · {{ selected.revision.mode === 'replace' ? '原任务编号保留，内容已更新' : '在该任务之前插入新内容' }}</p>
        <p v-for="task in selected.revision.moved_manual" :key="String(task.task_link_id)" class="hint">本次获准调整的手工时间：{{ task.title }}</p>
        <p v-for="warning in selected.revision.warnings" :key="warning" class="hint">{{ warning }}</p>
      </div>
      <ol><li v-for="(unit,i) in selected.units" :key="i"><strong>{{ unit.title }}</strong><span class="hint"> · {{ unit.minutes }} 分钟{{ unit.replace_content ? ' · 替换原步骤' : unit.existing_task_id ? ' · 已有任务' : ' · 新增内容' }}</span><p class="prose">{{ unit.outcome }}</p></li></ol>
      <button @click="detailGeneration++; selected = null">收起历史方案</button>
    </section>
  </article>
</template>

<style scoped>
.plan-history { padding:20px; border:1px solid var(--line); border-radius:14px; background:var(--bg-raise); margin:18px 0; }h2 { font-size:18px; margin:0 0 12px; }.hint { color:var(--ink-3); font-size:12px; line-height:1.7; }.history-list { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0; }button { border:1px solid var(--line); border-radius:8px; padding:9px 12px; color:var(--ink); background:var(--bg-app); cursor:pointer; }.history-list button { display:flex; flex-direction:column; gap:5px; text-align:left; }.history-list span { font-size:11px; color:var(--ink-3); }.history-detail { border-top:1px solid var(--line); padding-top:14px; margin-top:16px; }.before-content { border:1px solid var(--amber-border); border-radius:8px; padding:12px; margin:14px 0; }pre,.prose { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.8; font-family:inherit; font-size:13px; }pre { max-height:280px; overflow:auto; }ol { padding-left:22px; }li { margin:12px 0; }.error { color:var(--terra); }button:disabled { opacity:.5; }button:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }
</style>
