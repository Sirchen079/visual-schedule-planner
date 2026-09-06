<script setup lang="ts">
/**
 * 回收站视图（/trash，次导航）：任务回收站 + 资料回收站，B×C 暗色。
 * - 数据：GET /api/tasks/trash + GET /api/files/trash（本页局部状态，进页拉取）
 * - 恢复（restore）与彻底删除（purge，不可恢复）逐条进行 —— 后端无批量 purge 的 REST 端点
 *   （AI 工具 empty_trash 走审批门，不在本页），契约现状已记录
 * - 自动刷新：与壳层同款接线 —— watch run.phase 到 completed/cancelled 即重拉
 *   （AI delete_task/bulk_delete_* 落回收站后，本页无需手动刷新）
 */
import { onMounted, ref, watch } from 'vue'
import DomainState from '../components/domain/DomainState.vue'
import { listTrashTasks, purgeTask, restoreTask, type Task } from '../api/tasks'
import { humanSize, useLibraryStore } from '../stores/library'
import { datePart } from '../stores/tasks'
import { useRunStore } from '../stores/run'

const library = useLibraryStore()
const run = useRunStore()

/* ---- 任务回收站（本页局部状态：restore/purge 是一次性动作，不必进全局 store） ---- */
const trashTasks = ref<Task[] | null>(null)
const loadingTasks = ref(false)
const tasksError = ref<string | null>(null)
const busyTasks = ref<number[]>([])

async function loadTaskTrash(): Promise<void> {
  loadingTasks.value = true
  tasksError.value = null
  try {
    trashTasks.value = await listTrashTasks()
  } catch (e) {
    tasksError.value = e instanceof Error ? e.message : '任务回收站加载失败'
  } finally {
    loadingTasks.value = false
  }
}

async function restoreTaskRow(id: number): Promise<void> {
  busyTasks.value = [...busyTasks.value, id]
  tasksError.value = null
  try {
    await restoreTask(id)
    trashTasks.value = (trashTasks.value ?? []).filter((t) => t.id !== id)
  } catch (e) {
    tasksError.value = e instanceof Error ? e.message : '恢复失败'
  } finally {
    busyTasks.value = busyTasks.value.filter((x) => x !== id)
  }
}

async function purgeTaskRow(id: number): Promise<void> {
  busyTasks.value = [...busyTasks.value, id]
  tasksError.value = null
  try {
    await purgeTask(id)
    trashTasks.value = (trashTasks.value ?? []).filter((t) => t.id !== id)
  } catch (e) {
    tasksError.value = e instanceof Error ? e.message : '彻底删除失败'
  } finally {
    busyTasks.value = busyTasks.value.filter((x) => x !== id)
  }
}

const PRIORITY_LABEL: Record<string, string> = { high: '高', medium: '中', low: '低' }
function dueLabel(due: string | null): string {
  const d = datePart(due)
  return d ? `${Number(d.slice(0, 4))}/${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : '无日期'
}

function loadAll(): void {
  void loadTaskTrash()
  void library.loadTrash()
}

onMounted(() => {
  void loadTaskTrash()
  if (library.trash === null) void library.loadTrash()
})

/* run done 后自动刷新本页（与 App.vue 的壳层接线同款语义） */
watch(
  () => run.phase,
  (p, prev) => {
    if (prev && (p === 'completed' || p === 'cancelled')) void loadAll()
  },
)
</script>

<template>
  <section class="trash-view">
    <Teleport defer to="#head-actions">
      <button class="reload" @click="loadAll">刷新</button>
    </Teleport>

    <header class="tvv-head">
      <span class="tvv-caption">回收站</span>
      <span class="tvv-note">删除的任务与资料先进这里；「彻底删除」不可恢复。AI 写操作后自动刷新。</span>
    </header>

    <div class="panels">
      <!-- 任务回收站 -->
      <section class="panel">
        <header class="p-head">
          <span class="p-title">任务</span>
          <span v-if="trashTasks" class="p-count">{{ trashTasks.length }} 条</span>
        </header>
        <DomainState
          :loading="loadingTasks"
          loading-text="正在拉取任务回收站…"
          :error="tasksError"
          :empty="!loadingTasks && trashTasks !== null && trashTasks.length === 0"
          empty-title="空的"
          @retry="loadTaskTrash()"
        >
          删除的任务会在这里躺一段时间，随时可以捞回来。
        </DomainState>
        <ul v-if="trashTasks && trashTasks.length > 0" class="items">
          <li v-for="t in trashTasks" :key="t.id" class="item">
            <div class="it-main">
              <span class="it-name">{{ t.title }}</span>
              <span class="it-meta">截止 {{ dueLabel(t.due_date) }} · {{ PRIORITY_LABEL[t.priority] ?? t.priority }}优先</span>
            </div>
            <button class="act" :disabled="busyTasks.includes(t.id)" @click="restoreTaskRow(t.id)">恢复</button>
            <button class="act danger" :disabled="busyTasks.includes(t.id)" @click="purgeTaskRow(t.id)">彻底删除</button>
          </li>
        </ul>
      </section>

      <!-- 资料回收站 -->
      <section class="panel">
        <header class="p-head">
          <span class="p-title">资料</span>
          <span v-if="library.trash" class="p-count">{{ library.trash.length }} 件</span>
        </header>
        <DomainState
          :loading="library.loadingTrash"
          loading-text="正在拉取资料回收站…"
          :error="library.trashError"
          :empty="!library.loadingTrash && library.trash !== null && library.trash.length === 0"
          empty-title="空的"
          @retry="library.loadTrash()"
        >
          删除的资料会在这里躺一段时间，随时可以捞回来。
        </DomainState>
        <ul v-if="library.trash && library.trash.length > 0" class="items">
          <li v-for="f in library.trash" :key="f.id" class="item">
            <div class="it-main">
              <span class="it-name">{{ f.original_name }}</span>
              <span class="it-meta">{{ f.resource_type === 'link' ? '链接' : humanSize(f.size) }} · {{ f.uploaded_at.slice(0, 10) }}</span>
            </div>
            <button class="act" @click="library.restore(f.id)">恢复</button>
            <button class="act danger" @click="library.purge(f.id)">彻底删除</button>
          </li>
        </ul>
        <p v-if="library.actionError" class="p-error" role="alert">{{ library.actionError }}</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.trash-view {
  flex: 1;
  min-height: 0;
  padding: 18px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: auto;
}

.reload {
  font-size: 12.5px;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 4px 13px;
}
.reload:hover {
  border-color: var(--line-hover);
  color: var(--amber-soft);
}

.tvv-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.tvv-caption {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.tvv-note {
  font-size: 11.5px;
  color: var(--ink-3);
}

.panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  align-items: start;
}
.panel {
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--bg-raise);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 120px;
}
.p-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
  padding-bottom: 8px;
}
.p-title {
  font-family: var(--serif);
  font-size: 14.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.p-count {
  font-size: 11.5px;
  color: var(--ink-3);
}

.items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--line);
  background: var(--bg-app);
  border-radius: var(--radius-s);
  padding: 8px 11px;
}
.it-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.it-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.it-meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}
.act {
  flex: none;
  font-size: 11.5px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 10px;
}
.act:hover {
  border-color: var(--line-hover);
}
.act.danger {
  color: var(--terra-soft);
}
.act.danger:hover {
  border-color: var(--terra-dashed);
}
.act:disabled {
  /* 浅色 --ctl-disabled-opacity=0.75（禁用文字须 ≥3:1）；暗色 fallback 0.5 不变 */
  opacity: var(--ctl-disabled-opacity, 0.5);
  cursor: default;
}
.p-error {
  font-size: 12px;
  color: var(--terra-soft);
}
</style>
