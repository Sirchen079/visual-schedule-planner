<script setup lang="ts">
/**
 * 看板视图（/board，任务域）。
 * - 分组切换：按状态（待办/进行中/已完成三列）| 按截止日期（逾期/今天/明天/七天内/以后/无日期）
 * - 完成态切换：勾选框走 PATCH（乐观更新 + 失败回滚，回滚消息行内可见）
 * - 子任务清单：任务带 subtasks 时卡片内渲染，点击勾选切换 done（乐观 + 失败回滚）
 * - 新建任务：POST /api/tasks（标题必填，截止日/优先级可选）；软删除入回收站
 * - 数据：GET /api/tasks；run done 后由壳层自动刷新（App.vue 接线）
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import DomainState from '../components/domain/DomainState.vue'
import {
  DATE_BUCKETS,
  STATUS_COLUMNS,
  groupByDate,
  groupByStatus,
  useTasksStore,
  type DateBucket,
} from '../stores/tasks'
import { datePart } from '../stores/tasks'
import type { TaskPriority } from '../api/tasks'
import { toIsoDate } from '../utils/date'

const tasks = useTasksStore()
const route = useRoute()
const selectedTask = computed(() => {
  const value = route.query.task
  return typeof value === 'string' && /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : null
})
const visibleItems = computed(() => selectedTask.value ? (tasks.items ?? []).filter(t => t.id === selectedTask.value) : tasks.items ?? [])

type GroupMode = 'status' | 'date'
const groupMode = ref<GroupMode>('status')

const todayIso = toIsoDate(new Date())

const byStatus = computed(() => groupByStatus(visibleItems.value))
const byDate = computed(() => groupByDate(visibleItems.value, todayIso))

const PRIORITY_LABEL: Record<TaskPriority, string> = { high: '高', medium: '中', low: '低' }

function dueLabel(due: string | null, time: string | null): string {
  const d = datePart(due)
  if (!d) return ''
  const base = `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`
  return time ? `${base} ${time}` : base
}

function isOverdue(due: string | null, time: string | null, status: string): boolean {
  if (status === 'done') return false
  const d = datePart(due)
  if (!d) return false
  if (d < todayIso) return true
  if (d > todayIso || !time) return false
  const [h, m] = time.split(':').map(Number)
  const now = new Date()
  return h * 60 + m < now.getHours() * 60 + now.getMinutes()
}

/* ---- 新建任务 ---- */
const creating = ref(false)
const title = ref('')
const dueDate = ref('')
const priority = ref<TaskPriority>('medium')
const submitting = ref(false)

async function submit(): Promise<void> {
  const t = title.value.trim()
  if (!t || submitting.value) return
  submitting.value = true
  const ok = await tasks.create({
    title: t,
    due_date: dueDate.value || null,
    priority: priority.value,
  })
  submitting.value = false
  if (ok) {
    title.value = ''
    dueDate.value = ''
    priority.value = 'medium'
    creating.value = false
  }
}

onMounted(() => {
  if (tasks.items === null) void tasks.load()
})
</script>

<template>
  <section class="board-view">
    <div v-if="selectedTask" class="reminder-focus" role="status">
      <span>{{ tasks.items === null ? '正在查找提醒任务…' : visibleItems.length ? '正在查看通知对应的任务' : '此任务已删除或不再可用，原提醒保留在通知中。' }}</span>
      <RouterLink to="/board">查看全部任务 →</RouterLink>
    </div>
    <!-- 壳层内容头动作区：分组切换 -->
    <Teleport defer to="#head-actions">
      <div class="seg" role="tablist" aria-label="分组方式">
        <button :data-on="groupMode === 'status'" @click="groupMode = 'status'">按状态</button>
        <button :data-on="groupMode === 'date'" @click="groupMode = 'date'">按日期</button>
      </div>
      <button class="new-btn" @click="creating = !creating">
        <AppIcon name="plus" :size="14" />
        {{ creating ? '收起' : '新建任务' }}
      </button>
    </Teleport>

    <!-- 统计行（≥3 处差异信息：总量/进行中/逾期） -->
    <div v-if="tasks.stats" class="stats">
      <div class="st"><span class="n">{{ tasks.stats.total }}</span><span class="l">全部</span></div>
      <div class="st"><span class="n">{{ tasks.stats.todo }}</span><span class="l">待办</span></div>
      <div class="st"><span class="n" :data-tone="tasks.stats.doing > 0 ? 'amber' : ''">{{ tasks.stats.doing }}</span><span class="l">进行中</span></div>
      <div class="st"><span class="n">{{ tasks.stats.done }}</span><span class="l">已完成</span></div>
      <div class="st"><span class="n" :data-tone="tasks.stats.overdue > 0 ? 'terra' : ''">{{ tasks.stats.overdue }}</span><span class="l">已逾期</span></div>
      <div class="st"><span class="n">{{ tasks.stats.dueToday }}</span><span class="l">今日到期</span></div>
      <span v-if="tasks.lastRefreshedAt" class="refreshed">已就绪 · AI 写操作后自动刷新</span>
    </div>

    <!-- 操作失败后的回滚提示 -->
    <div v-if="tasks.actionError" class="action-error" role="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ tasks.actionError }}</span>
    </div>

    <!-- 新建表单 -->
    <form v-if="creating" class="creator" @submit.prevent="submit">
      <input v-model="title" class="in title-in" placeholder="任务标题（必填）" aria-label="任务标题" />
      <input v-model="dueDate" class="in date-in" type="date" aria-label="截止日期" />
      <select v-model="priority" class="in prio-in" aria-label="优先级">
        <option value="high">高优先</option>
        <option value="medium">中优先</option>
        <option value="low">低优先</option>
      </select>
      <button class="submit" type="submit" :disabled="!title.trim() || submitting">
        {{ submitting ? '创建中…' : '创建' }}
      </button>
    </form>

    <DomainState
      :loading="tasks.loading && tasks.items === null"
      loading-text="正在拉取任务列表…"
      :error="tasks.error"
      :empty="!tasks.loading && tasks.items !== null && tasks.items.length === 0"
      empty-title="任务栏空着"
      @retry="tasks.load()"
    >
      对左侧的知时说一句「帮我建个任务」，或点右上「新建任务」——<br />任务会在这里按状态/日期落位，勾选即完成。
    </DomainState>

    <!-- 看板列 -->
    <div v-if="tasks.items && tasks.items.length > 0" class="columns" :data-mode="groupMode">
      <template v-if="groupMode === 'status'">
        <section v-for="col in STATUS_COLUMNS" :key="col.key" class="column">
          <header class="col-head">
            <span class="col-title">{{ col.label }}</span>
            <span class="col-count">{{ byStatus[col.key].length }}</span>
          </header>
          <p v-if="byStatus[col.key].length === 0" class="col-empty">暂无{{ col.label }}任务</p>
          <article v-for="t in byStatus[col.key]" :key="t.id" class="card" :data-status="t.status">
            <button
              class="tick"
              :aria-label="t.status === 'done' ? '标记为待办' : '标记为完成'"
              :disabled="tasks.pendingIds.includes(t.id)"
              @click="tasks.toggleDone(t.id)"
            >
              <AppIcon v-if="t.status === 'done'" name="check" :size="15" />
            </button>
            <div class="card-main">
              <div class="card-title" :data-done="t.status === 'done'">{{ t.title }}</div>
              <div class="card-meta">
                <span
                  v-if="dueLabel(t.due_date, t.due_time)"
                  class="due"
                  :data-overdue="isOverdue(t.due_date, t.due_time, t.status)"
                >{{ dueLabel(t.due_date, t.due_time) }} 截止</span>
                <span class="prio" :data-prio="t.priority">{{ PRIORITY_LABEL[t.priority] }}优先</span>
                <span v-if="t.estimated_minutes" class="est">{{ t.estimated_minutes }} 分钟</span>
                <span v-for="tag in t.tags" :key="tag" class="tag">{{ tag }}</span>
              </div>
              <ul v-if="t.subtasks && t.subtasks.length > 0" class="subs" aria-label="子任务">
                <li v-for="s in t.subtasks" :key="s.id">
                  <button
                    class="sub-tick"
                    :data-done="s.done"
                    :disabled="tasks.pendingSubIds.includes(s.id)"
                    :aria-label="s.done ? `标记子任务「${s.title}」为未完成` : `标记子任务「${s.title}」为完成`"
                    @click="tasks.toggleSubtask(t.id, s.id)"
                  >
                    <AppIcon v-if="s.done" name="check" :size="10" />
                  </button>
                  <span class="sub-title" :data-done="s.done">{{ s.title }}</span>
                  <span v-if="s.estimated_minutes" class="sub-est">{{ s.estimated_minutes }} 分钟</span>
                </li>
              </ul>
            </div>
            <button class="del" :aria-label="`删除任务 ${t.title}`" title="删除（入回收站）" @click="tasks.remove(t.id)">
              <AppIcon name="x" :size="13" />
            </button>
          </article>
        </section>
      </template>

      <template v-else>
        <section v-for="b in DATE_BUCKETS" :key="b.key" class="column" :data-bucket="b.key">
          <header class="col-head">
            <span class="col-title" :data-tone="b.key === 'overdue' ? 'terra' : b.key === 'today' ? 'amber' : ''">{{ b.label }}</span>
            <span class="col-count">{{ byDate[b.key as DateBucket].length }}</span>
          </header>
          <p v-if="byDate[b.key as DateBucket].length === 0" class="col-empty">—</p>
          <article
            v-for="t in byDate[b.key as DateBucket]"
            :key="t.id"
            class="card"
            :data-status="t.status"
          >
            <button
              class="tick"
              :aria-label="t.status === 'done' ? '标记为待办' : '标记为完成'"
              :disabled="tasks.pendingIds.includes(t.id)"
              @click="tasks.toggleDone(t.id)"
            >
              <AppIcon v-if="t.status === 'done'" name="check" :size="15" />
            </button>
            <div class="card-main">
              <div class="card-title" :data-done="t.status === 'done'">{{ t.title }}</div>
              <div class="card-meta">
                <span v-if="dueLabel(t.due_date, t.due_time)" class="due">{{ dueLabel(t.due_date, t.due_time) }} 截止</span>
                <span class="prio" :data-prio="t.priority">{{ PRIORITY_LABEL[t.priority] }}优先</span>
                <span v-for="tag in t.tags" :key="tag" class="tag">{{ tag }}</span>
              </div>
              <ul v-if="t.subtasks && t.subtasks.length > 0" class="subs" aria-label="子任务">
                <li v-for="s in t.subtasks" :key="s.id">
                  <button
                    class="sub-tick"
                    :data-done="s.done"
                    :disabled="tasks.pendingSubIds.includes(s.id)"
                    :aria-label="s.done ? `标记子任务「${s.title}」为未完成` : `标记子任务「${s.title}」为完成`"
                    @click="tasks.toggleSubtask(t.id, s.id)"
                  >
                    <AppIcon v-if="s.done" name="check" :size="10" />
                  </button>
                  <span class="sub-title" :data-done="s.done">{{ s.title }}</span>
                  <span v-if="s.estimated_minutes" class="sub-est">{{ s.estimated_minutes }} 分钟</span>
                </li>
              </ul>
            </div>
            <button class="del" :aria-label="`删除任务 ${t.title}`" title="删除（入回收站）" @click="tasks.remove(t.id)">
              <AppIcon name="x" :size="13" />
            </button>
          </article>
        </section>
      </template>
    </div>
  </section>
</template>

<style scoped>
.reminder-focus { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:12px 16px; margin-bottom:16px; border:1px solid var(--amber); border-radius:10px; font-size:13px; }
.reminder-focus a { color:var(--amber); white-space:nowrap; }
.board-view {
  flex: 1;
  min-height: 0;
  padding: 18px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 壳头控件（与 CalendarView 的 .seg 同语言） */
.seg {
  display: flex;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  overflow: hidden;
}
.seg button {
  font-size: 12.5px;
  color: var(--ink-3);
  padding: 4px 12px;
}
.seg button + button {
  border-left: 1px solid var(--line-2);
}
.seg button[data-on='true'] {
  background: var(--amber-wash);
  color: var(--amber-soft);
  font-weight: 600;
}
.new-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--btn-new-text);
  background: var(--btn-new-bg);
  border-radius: var(--radius-pill);
  padding: 5px 13px;
}
.new-btn:hover {
  background: var(--btn-new-bg-hover);
}

/* 统计行 */
.stats {
  display: flex;
  align-items: center;
  gap: 22px;
  border: 1px solid var(--line);
  background: var(--bg-sink);
  border-radius: var(--radius-m);
  padding: 10px 16px;
}
.st {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.st .n {
  font-family: var(--serif);
  font-size: 20px;
  font-weight: 600;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
.st .n[data-tone='amber'] {
  color: var(--amber-soft);
}
.st .n[data-tone='terra'] {
  color: var(--terra-soft);
}
.st .l {
  font-size: 11.5px;
  color: var(--ink-3);
  letter-spacing: 0.06em;
}
.refreshed {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--ink-3);
}

.action-error {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--terra-soft);
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 8px 12px;
}

/* 新建表单 */
.creator {
  display: flex;
  gap: 8px;
  border: 1px solid var(--line-2);
  background: var(--bg-raise);
  border-radius: var(--radius-m);
  padding: 10px;
}
.in {
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink);
  background: var(--bg-sink);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 6px 10px;
  box-shadow: var(--shadow-input);
}
.in::placeholder {
  color: var(--ink-faint);
}
.in:focus {
  outline: none;
  border-color: var(--line-hover);
}
.title-in {
  flex: 1;
  min-width: 120px;
}
.date-in {
  color-scheme: dark;
}
.submit {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--btn-ok-text);
  background: var(--amber);
  border-radius: var(--radius-s);
  padding: 6px 14px;
}
.submit:disabled {
  background: var(--send-idle-bg);
  color: var(--send-idle-text);
  cursor: default;
}

/* 看板列 */
.columns {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 14px;
  overflow: auto;
  align-items: flex-start;
}
.columns[data-mode='date'] .column {
  flex: 1 0 240px;
}
.column {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--bg-raise);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.col-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
  padding-bottom: 8px;
}
.col-title {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.col-title[data-tone='amber'] {
  color: var(--amber-soft);
}
.col-title[data-tone='terra'] {
  color: var(--terra-soft);
}
.col-count {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-3);
}
.col-empty {
  font-size: 12px;
  color: var(--ink-3);
  font-style: italic;
  padding: 4px 2px 8px;
}

/* 任务卡 */
.card {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  border: 1px solid var(--line-2);
  background: var(--bg-app);
  border-radius: var(--radius-s);
  padding: 9px 10px;
}
.card[data-status='done'] {
  opacity: 0.62;
}
.card[data-status='doing'] {
  border-color: var(--amber-border-weak);
}
.tick {
  flex: none;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  border: 1.5px solid var(--line-hover);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--btn-ok-text);
}
.tick:hover {
  border-color: var(--amber-dim);
}
.tick:disabled {
  opacity: 0.5;
  cursor: default;
}
.card[data-status='done'] .tick {
  background: var(--ok);
  border-color: var(--ok);
}
.card-main {
  flex: 1;
  min-width: 0;
}
.card-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.45;
  word-break: break-word;
}
.card-title[data-done='true'] {
  text-decoration: line-through;
  text-decoration-color: var(--ink-3);
  color: var(--ink-2);
  font-weight: 500;
}
.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 10px;
  margin-top: 5px;
}
.card-meta > span {
  font-size: 11.5px;
  color: var(--ink-3);
}
.due {
  font-family: var(--mono);
}
.due[data-overdue='true'] {
  color: var(--terra-soft);
  font-weight: 600;
}
.prio[data-prio='high'] {
  color: var(--terra-soft);
  font-weight: 600;
}
.prio[data-prio='medium'] {
  color: var(--amber-dim);
}
.tag {
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 0 7px;
}

/* 子任务清单（父任务带 subtasks 时才渲染；点击勾选切换完成态） */
.subs {
  list-style: none;
  margin: 7px 0 0;
  padding: 7px 0 0;
  border-top: 1px dashed var(--line);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.subs li {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.sub-tick {
  flex: none;
  width: 15px;
  height: 15px;
  border: 1.2px solid var(--line-hover);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--btn-ok-text);
}
.sub-tick:hover {
  border-color: var(--amber-dim);
}
.sub-tick:disabled {
  opacity: 0.5;
  cursor: default;
}
.sub-tick[data-done='true'] {
  background: var(--ok);
  border-color: var(--ok);
}
.sub-title {
  font-size: 12px;
  color: var(--ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sub-title[data-done='true'] {
  text-decoration: line-through;
  text-decoration-color: var(--ink-3);
  color: var(--ink-3);
}
.sub-est {
  flex: none;
  font-size: 10.5px;
  color: var(--ink-3);
}
.del {
  flex: none;
  color: var(--ink-3);
  border-radius: var(--radius-s);
  padding: 3px;
}
.del:hover {
  color: var(--terra-soft);
}
</style>
