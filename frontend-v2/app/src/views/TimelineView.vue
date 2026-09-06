<script setup lang="ts">
/** 未来 14 天的任务截止日期与排期负载。
 * /range 提供任务排期，独立日程显示在日历页。子任务支持乐观更新及失败回滚。 */
import { onMounted } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import DomainState from '../components/domain/DomainState.vue'
import { useTasksStore } from '../stores/tasks'
import { toIsoDate } from '../utils/date'

const tasks = useTasksStore()
const todayIso = toIsoDate(new Date())
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']

function dayHead(iso: string): { m: number; d: number; wd: string; rel: string } {
  const d = new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)))
  const rel = iso === todayIso ? '今天' : ''
  return { m: d.getMonth() + 1, d: d.getDate(), wd: `星期${WEEKDAYS[d.getDay()]}`, rel }
}

function dueTime(task: { due_time: string | null }): string {
  return task.due_time ? ` ${task.due_time}` : ''
}

function loadAll(): void {
  void tasks.load()
  void tasks.loadRange()
}

onMounted(() => {
  if (tasks.items === null) void tasks.load()
  if (tasks.range === null) void tasks.loadRange()
})
</script>

<template>
  <section class="tl-view">
    <header class="tl-head">
      <span class="tl-caption">未来 {{ tasks.rangeDays }} 天 · 任务截止与排程负载</span>
      <span v-if="tasks.loadingRange" class="tl-note">正在拉取任务负载…</span>
      <span v-else-if="tasks.range" class="tl-note">已就绪 · AI 写操作后自动刷新</span>
    </header>

    <div v-if="tasks.rangeError" class="tl-error" role="alert">
      <span>{{ tasks.rangeError }}</span>
      <button class="retry" @click="tasks.loadRange()">重试</button>
    </div>

    <DomainState
      :loading="tasks.loading && tasks.items === null"
      loading-text="正在拉取任务…"
      :error="tasks.error"
      :empty="tasks.timeline !== null && tasks.timeline.every((day) => day.dueTasks.length === 0 && day.scheduled.length === 0)"
      empty-title="时间轴上还没有落点"
      @retry="loadAll()"
    >
      给任务设上截止日期，或让知时把任务排到某天（「明天下午复习两小时」），<br />它们就会沿这条时间轴依次亮起。
    </DomainState>

    <div v-if="tasks.timeline" class="tl-rows">
      <section
        v-for="day in tasks.timeline"
        :key="day.date"
        class="tl-row"
        :data-today="day.date === todayIso"
      >
        <div class="tl-date">
          <span class="d-num">{{ dayHead(day.date).m }}/{{ dayHead(day.date).d }}</span>
          <span class="d-wd">{{ dayHead(day.date).wd }}</span>
          <span v-if="dayHead(day.date).rel" class="d-rel">{{ dayHead(day.date).rel }}</span>
        </div>

        <div class="tl-body" :data-empty="day.dueTasks.length === 0 && day.scheduled.length === 0">
          <!-- 排程负载（range：任务排期明细） -->
          <div v-for="item in day.scheduled" :key="`s-${item.task_id ?? item.title}-${item.start_time ?? ''}`" class="slot">
            <span class="s-time">{{ item.start_time ?? '—' }}<template v-if="item.end_time">–{{ item.end_time }}</template></span>
            <span class="s-title">{{ item.title }}</span>
            <span v-if="item.estimated_minutes" class="s-est">{{ item.estimated_minutes }} 分钟</span>
          </div>
          <!-- 该日截止任务 -->
          <div v-for="t in day.dueTasks" :key="`t-${t.id}`" class="due" :data-done="t.status === 'done'">
            <span class="due-tag">截止</span>
            <span class="s-title">{{ t.title }}</span>
            <span class="s-time">{{ dueTime(t) || ' 全天' }}</span>
            <ul v-if="t.subtasks && t.subtasks.length > 0" class="due-subs" aria-label="子任务">
              <li v-for="s in t.subtasks" :key="s.id">
                <button
                  class="sub-tick"
                  :data-done="s.done"
                  :disabled="tasks.pendingSubIds.includes(s.id)"
                  :aria-label="s.done ? `标记子任务「${s.title}」为未完成` : `标记子任务「${s.title}」为完成`"
                  @click="tasks.toggleSubtask(t.id, s.id)"
                >
                  <AppIcon v-if="s.done" name="check" :size="9" />
                </button>
                <span class="sub-title" :data-done="s.done">{{ s.title }}</span>
              </li>
            </ul>
          </div>
          <p v-if="day.dueTasks.length === 0 && day.scheduled.length === 0" class="tl-free">无安排</p>
        </div>

        <div class="tl-load" :title="`预估负载 ${day.estimatedMinutes} 分钟`">
          <div class="load-bar">
            <div class="load-fill" :data-heavy="day.estimatedMinutes >= 240 ? '' : null" :style="{ width: `${Math.min(100, (day.estimatedMinutes / 480) * 100)}%` }" />
          </div>
          <span class="load-num">{{ day.estimatedMinutes > 0 ? `${day.estimatedMinutes}′` : '—' }}</span>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.tl-view {
  flex: 1;
  min-height: 0;
  padding: 18px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}
.tl-head {
  display: flex;
  align-items: baseline;
  gap: 14px;
}
.tl-caption {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.tl-note {
  font-size: 11.5px;
  color: var(--ink-3);
}
.tl-error {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  color: var(--terra-soft);
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 8px 12px;
}
.retry {
  font-size: 12px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 2px 10px;
}
.retry:hover {
  border-color: var(--line-hover);
}

.tl-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tl-row {
  display: grid;
  grid-template-columns: 108px 1fr 130px;
  gap: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--bg-raise);
  padding: 10px 14px;
  align-items: center;
}
.tl-row[data-today='true'] {
  border-color: var(--amber-border-weak);
  background: var(--bg-runbar);
}

/* 日期刊头 */
.tl-date {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.d-num {
  font-family: var(--serif);
  font-size: 19px;
  font-weight: 600;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.tl-row[data-today='true'] .d-num {
  color: var(--amber-soft);
}
.d-wd {
  font-size: 11.5px;
  color: var(--ink-3);
}
.d-rel {
  font-size: 11px;
  font-weight: 600;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border);
  border-radius: var(--radius-pill);
  padding: 0 7px;
  align-self: flex-start;
}

/* 当日条目 */
.tl-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.tl-body[data-empty='true'] {
  display: block;
}
.slot,
.due {
  display: flex;
  align-items: baseline;
  gap: 9px;
  min-width: 0;
}
.s-time {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--amber-dim);
  flex: none;
}
.s-title {
  font-size: 13px;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.s-est {
  font-size: 11.5px;
  color: var(--ink-3);
  flex: none;
}
.due {
  border-left: 2px solid var(--amber-dim);
  padding-left: 9px;
  flex-wrap: wrap;
}
.due[data-done='true'] {
  opacity: 0.55;
  border-left-color: var(--ok);
}
.due-tag {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--amber-soft);
  flex: none;
}

/* 子任务清单（父任务带 subtasks 时才渲染；点击勾选切换完成态） */
.due-subs {
  flex: 1 1 100%;
  list-style: none;
  margin: 3px 0 0;
  padding: 5px 0 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.due-subs li {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.sub-tick {
  flex: none;
  width: 14px;
  height: 14px;
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
  font-size: 11.5px;
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
.tl-free {
  font-size: 12px;
  color: var(--ink-3);
  font-style: italic;
}

/* 负载条（480 分钟 ≈ 满格；≥240 视为重载日） */
.tl-load {
  display: flex;
  align-items: center;
  gap: 8px;
}
.load-bar {
  flex: 1;
  height: 5px;
  border-radius: var(--radius-pill);
  background: var(--bg-sink);
  border: 1px solid var(--line);
  overflow: hidden;
}
.load-fill {
  height: 100%;
  background: var(--amber-dim);
  border-radius: var(--radius-pill);
}
.load-fill[data-heavy] {
  background: var(--terra);
}
.load-num {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
  width: 38px;
  text-align: right;
}
</style>
