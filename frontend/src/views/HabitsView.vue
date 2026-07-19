<script setup>
// 习惯打卡视图：数据自取自管（无 props），打卡/撤销乐观更新，失败回退重拉。
import { inject, onMounted, reactive, ref } from 'vue'
import {
  checkHabit,
  createHabit,
  deleteHabit,
  getHabitLogs,
  listHabits,
  uncheckHabit,
  updateHabit,
} from '../api/habits'
import { askAssistant } from '../utils/assistant'
import ArtIcon from '../components/ArtIcon.vue'
import AppSpinner from '../components/ui/AppSpinner.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import PageHeader from '../components/ui/PageHeader.vue'
import SegmentedControl from '../components/ui/SegmentedControl.vue'

const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })

// 「问助手点评」：让 AI 基于打卡现状给出保持动力与防断签的建议
function reviewHabits() {
  askAssistant(
    '看看我现在的习惯打卡情况：各习惯的连续纪录、断签风险、目标次数设置是否合理。' +
      '给我保持动力的具体建议；如果有适合我的新习惯，也可以推荐并帮我创建。'
  )
}
const confirmDialog = inject(
  'confirm-dialog',
  (o) => Promise.resolve(window.confirm(o.message || ''))
)

const PALETTE = ['#74ccf2', '#a5f2c1', '#fbbf7a', '#c4a5f2', '#f2a5c4', '#7fd4c4', '#f2d479']
const PERIOD_OPTIONS = [
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
]
const HEAT_DAYS = 84 // 近 12 周

const habits = ref([])
const loading = ref(true)

function fmtDate(d) {
  const m = `${d.getMonth() + 1}`.padStart(2, '0')
  const day = `${d.getDate()}`.padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    habits.value = await listHabits()
  } catch (e) {
    toast.error(`习惯列表加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}
onMounted(() => load())

// ---- 打卡 / 撤销：本地先改，成功用服务端返回对齐（streak 由后端计算），失败 toast 并重拉回退 ----
function patchLocal(h, delta) {
  h.today_count = Math.max(0, h.today_count + delta)
  h.period_count = Math.max(0, h.period_count + delta)
  h.done_today = h.period_count >= h.target_count
}

function applyServer(updated) {
  const i = habits.value.findIndex((x) => x.id === updated.id)
  if (i !== -1) habits.value[i] = updated
}

async function onCheck(h) {
  patchLocal(h, 1)
  bumpLogToday(h.id, 1)
  try {
    applyServer(await checkHabit(h.id))
  } catch (e) {
    toast.error(`打卡失败：${e.message}`)
    await load(true)
  }
}

async function onUncheck(h) {
  if (h.today_count <= 0) return
  patchLocal(h, -1)
  bumpLogToday(h.id, -1)
  try {
    applyServer(await uncheckHabit(h.id))
  } catch (e) {
    toast.error(`撤销失败：${e.message}`)
    await load(true)
  }
}

function progressPct(h) {
  return Math.min(100, Math.round((h.period_count / Math.max(1, h.target_count)) * 100))
}

// ---- 近 12 周热力：点击卡片展开，按周列对齐（周一开头），未来天不渲染 ----
const expandedId = ref(null)
const logsMap = ref({}) // habitId -> [{ date, count }]
const logsLoadingId = ref(null)

async function toggleExpand(h) {
  if (expandedId.value === h.id) {
    expandedId.value = null
    return
  }
  expandedId.value = h.id
  if (logsMap.value[h.id]) return
  logsLoadingId.value = h.id
  try {
    const logs = await getHabitLogs(h.id, HEAT_DAYS)
    logsMap.value = { ...logsMap.value, [h.id]: logs }
  } catch (e) {
    toast.error(`打卡记录加载失败：${e.message}`)
  } finally {
    logsLoadingId.value = null
  }
}

// 打卡/撤销只影响今天，已加载的热力缓存同步改今日格，保持展开状态一致
function bumpLogToday(id, delta) {
  const logs = logsMap.value[id]
  if (!logs) return
  const today = fmtDate(new Date())
  const entry = logs.find((l) => l.date === today)
  if (entry) entry.count = Math.max(0, entry.count + delta)
  else if (delta > 0) logs.push({ date: today, count: delta })
}

function heatWeeks(h) {
  const counts = new Map((logsMap.value[h.id] || []).map((l) => [l.date, l.count]))
  const end = new Date()
  end.setHours(0, 0, 0, 0)
  const start = new Date(end)
  start.setDate(start.getDate() - (HEAT_DAYS - 1))
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7)) // 对齐到周一
  const weeks = []
  const cursor = new Date(start)
  while (cursor <= end) {
    const week = []
    for (let i = 0; i < 7; i++) {
      if (cursor > end) {
        week.push(null)
      } else {
        const key = fmtDate(cursor)
        week.push({ date: key, count: counts.get(key) || 0 })
      }
      cursor.setDate(cursor.getDate() + 1)
    }
    weeks.push(week)
  }
  return weeks
}

// 三档上色：0 次走默认底色，1 次浅色，2+ 次实心习惯色
function cellStyle(h, cell) {
  if (!cell || !cell.count) return {}
  const c = h.color || PALETTE[0]
  return { background: cell.count >= 2 ? c : `color-mix(in srgb, ${c} 45%, transparent)` }
}

// ---- 新建 / 编辑弹窗 ----
const modalOpen = ref(false)
const editing = ref(null)
const saving = ref(false)
const formError = ref('')
const form = reactive({ name: '', notes: '', period: 'daily', target_count: 1, color: PALETTE[0] })

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', notes: '', period: 'daily', target_count: 1, color: PALETTE[0] })
  formError.value = ''
  modalOpen.value = true
}

function openEdit(h) {
  editing.value = h
  Object.assign(form, {
    name: h.name,
    notes: h.notes || '',
    period: h.period,
    target_count: h.target_count,
    color: h.color || PALETTE[0],
  })
  formError.value = ''
  modalOpen.value = true
}

function closeModal() {
  modalOpen.value = false
  editing.value = null
}

async function save() {
  const name = form.name.trim()
  if (!name) {
    formError.value = '请填写习惯名称'
    return
  }
  const payload = {
    name,
    notes: form.notes.trim(),
    period: form.period,
    target_count: Math.min(99, Math.max(1, Number(form.target_count) || 1)),
    color: form.color,
  }
  saving.value = true
  try {
    if (editing.value) {
      await updateHabit(editing.value.id, payload)
      toast.success(`已保存「${name}」`)
    } else {
      await createHabit(payload)
      toast.success(`已创建「${name}」`)
    }
    closeModal()
    await load(true)
  } catch (e) {
    toast.error(`保存失败：${e.message}`)
  } finally {
    saving.value = false
  }
}

async function removeHabit() {
  const h = editing.value
  if (!h) return
  const ok = await confirmDialog({
    title: '删除习惯',
    message: `「${h.name}」将被删除，历史打卡记录会一并清除。`,
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteHabit(h.id)
    toast.success(`已删除「${h.name}」`)
    closeModal()
    await load(true)
  } catch (e) {
    toast.error(`删除失败：${e.message}`)
  }
}
</script>

<template>
  <div class="habits workspace-page">
    <PageHeader icon="steps" title="习惯打卡" subtitle="每天一点点，连续就是力量。">
      <template #actions>
        <button class="ghost" @click="reviewHabits">问助手点评</button>
        <button class="create-btn" @click="openCreate">
          <ArtIcon name="plus" tone="on-accent" :size="20" />
          <span>新建习惯</span>
        </button>
      </template>
    </PageHeader>

    <div v-if="loading" class="loading-wrap">
      <AppSpinner label="加载习惯" />
    </div>

    <EmptyState
      v-else-if="!habits.length"
      icon="steps"
      title="还没有习惯"
      hint="从一个小到不可能失败的习惯开始。"
    >
      <button type="button" class="empty-create" @click="openCreate">
        <ArtIcon name="plus" tone="on-accent" :size="16" />
        <span>新建习惯</span>
      </button>
    </EmptyState>

    <div v-else class="habits-grid">
      <article
        v-for="(h, i) in habits"
        :key="h.id"
        class="habit-card section-panel animate-in"
        :class="{ expanded: expandedId === h.id }"
        :style="{ animationDelay: `${i * 0.05}s` }"
        @click="toggleExpand(h)"
      >
        <span class="habit-strip" :style="{ background: h.color }"></span>
        <div class="habit-inner">
          <div class="habit-head">
            <span class="habit-dot" :style="{ background: h.color }"></span>
            <div class="habit-name">
              <h3>{{ h.name }}</h3>
              <p v-if="h.notes" class="muted">{{ h.notes }}</p>
            </div>
            <span
              v-if="h.streak > 0"
              class="streak-badge"
              :style="{
                background: `color-mix(in srgb, ${h.color || PALETTE[0]} 18%, transparent)`,
                borderColor: `color-mix(in srgb, ${h.color || PALETTE[0]} 36%, transparent)`,
              }"
            >
              连续 {{ h.streak }} {{ h.period === 'daily' ? '天' : '周' }}
            </span>
          </div>

          <div class="habit-main">
            <div class="habit-progress">
              <span class="progress-text">
                {{ h.period === 'daily' ? '今日' : '本周' }} {{ h.period_count }}/{{ h.target_count }} 次
              </span>
              <div class="progress-track">
                <div
                  class="progress-fill"
                  :class="{ done: h.done_today }"
                  :style="{ width: `${progressPct(h)}%`, background: h.color }"
                ></div>
              </div>
            </div>
            <div class="habit-actions" @click.stop>
              <button
                type="button"
                class="check-btn"
                :class="{ done: h.done_today }"
                @click="onCheck(h)"
              >
                {{ h.done_today ? '已达标 ✓' : '打卡一次' }}
              </button>
              <button
                type="button"
                class="ghost link-btn"
                :disabled="h.today_count <= 0"
                @click="onUncheck(h)"
              >
                撤销
              </button>
              <button type="button" class="ghost link-btn" @click="openEdit(h)">编辑</button>
            </div>
          </div>

          <div v-if="expandedId === h.id" class="habit-heat" @click.stop>
            <div class="heat-head">
              <span class="muted">近 12 周打卡</span>
              <span class="muted heat-hint">颜色越深次数越多</span>
            </div>
            <div v-if="logsLoadingId === h.id" class="heat-loading">
              <AppSpinner size="sm" label="加载记录" />
            </div>
            <div v-else class="heat-grid" role="img" :aria-label="`${h.name} 近 12 周打卡热力`">
              <div class="heat-week" v-for="(week, wi) in heatWeeks(h)" :key="wi">
                <span
                  v-for="(cell, di) in week"
                  :key="di"
                  class="heat-cell"
                  :class="{ future: !cell }"
                  :style="cellStyle(h, cell)"
                  :title="cell ? `${cell.date} · 打卡 ${cell.count} 次` : ''"
                ></span>
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>

    <BaseModal
      :open="modalOpen"
      size="sm"
      :label="editing ? '编辑习惯' : '新建习惯'"
      @close="closeModal"
    >
      <div class="habit-modal">
        <div class="modal-head">
          <div class="modal-title">{{ editing ? '编辑习惯' : '新建习惯' }}</div>
        </div>
        <form class="habit-form" @submit.prevent="save">
          <div class="field">
            <label>名称 <span class="required">*</span></label>
            <input
              v-model="form.name"
              placeholder="如：喝水、阅读、跑步"
              data-autofocus
              :class="{ invalid: formError }"
            />
            <p v-if="formError" class="field-error">{{ formError }}</p>
          </div>

          <div class="field">
            <label>周期</label>
            <SegmentedControl v-model="form.period" :options="PERIOD_OPTIONS" />
          </div>

          <div class="field">
            <label>目标次数</label>
            <div class="target-row">
              <input type="number" min="1" max="99" v-model.number="form.target_count" />
              <span class="muted target-hint">
                {{ form.period === 'daily' ? '每天' : '每周' }} {{ form.target_count || 1 }} 次
              </span>
            </div>
          </div>

          <div class="field">
            <label>备注</label>
            <textarea v-model="form.notes" rows="3" placeholder="提醒自己为什么开始…"></textarea>
          </div>

          <div class="field">
            <label>颜色</label>
            <div class="palette">
              <button
                v-for="c in PALETTE"
                :key="c"
                type="button"
                class="swatch"
                :class="{ active: form.color === c }"
                :style="{ background: c }"
                :aria-label="`选择颜色 ${c}`"
                :aria-pressed="form.color === c"
                @click="form.color = c"
              ></button>
            </div>
          </div>

          <div class="actions">
            <button v-if="editing" type="button" class="danger" @click="removeHabit">删除</button>
            <span class="actions-spacer"></span>
            <button type="button" class="ghost" @click="closeModal">取消</button>
            <button type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
          </div>
        </form>
      </div>
    </BaseModal>
  </div>
</template>

<style scoped>
.habits {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 根节点已有 gap，去掉 PageHeader 自带下间距避免叠加 */
.habits :deep(.page-header) {
  margin-bottom: 0;
}

.create-btn,
.empty-create {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.create-btn {
  padding: 11px 22px;
}

.create-btn :deep(.art-icon) {
  transition: transform 0.2s ease;
}

.create-btn:hover :deep(.art-icon) {
  transform: rotate(90deg);
}

.loading-wrap {
  display: grid;
  place-items: center;
  min-height: 220px;
}

.habits-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 16px;
  align-items: start;
}

.habit-card {
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.habit-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
  border-color: var(--border-strong);
}

.habit-card.expanded {
  grid-column: 1 / -1;
}

/* 卡片顶部细条用习惯色 */
.habit-strip {
  display: block;
  height: 4px;
  width: 100%;
}

.habit-inner {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px 16px 16px;
}

.habit-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.habit-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 5px;
  box-shadow: var(--shadow-xs);
}

.habit-name {
  min-width: 0;
  flex: 1;
}

.habit-name h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.habit-name p {
  margin: 3px 0 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.streak-badge {
  flex-shrink: 0;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 650;
  color: var(--text);
  white-space: nowrap;
}

.habit-main {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.habit-progress {
  flex: 1;
  min-width: 140px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.progress-text {
  font-size: 13px;
  font-weight: 650;
  color: var(--text-soft);
}

.progress-track {
  height: 8px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  overflow: hidden;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.05);
}

.progress-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  transition: width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.habit-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 已达标态：绿色描边，仍可继续打卡 */
.check-btn.done {
  background: transparent;
  color: var(--success);
  border-color: color-mix(in srgb, var(--success) 55%, transparent);
}

.check-btn.done:hover {
  background: color-mix(in srgb, var(--success) 10%, transparent);
  border-color: var(--success);
}

.link-btn {
  padding: 6px 10px;
  font-size: 12px;
}

.habit-heat {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  cursor: default;
}

.heat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.heat-hint {
  font-size: 12px;
}

.heat-loading {
  display: grid;
  place-items: center;
  min-height: 80px;
}

.heat-grid {
  display: flex;
  gap: 3px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.heat-week {
  display: grid;
  grid-template-rows: repeat(7, 12px);
  gap: 3px;
}

.heat-cell {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: var(--surface-3);
}

.heat-cell.future {
  visibility: hidden;
}

/* ---- 新建 / 编辑弹窗 ---- */
.habit-modal {
  padding: 22px;
}

.modal-head {
  margin-bottom: 16px;
}

.modal-title {
  font-size: 17px;
  font-weight: 800;
  color: var(--text);
}

.habit-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.field label {
  font-size: 13px;
  color: var(--text-soft);
  font-weight: 600;
}

.required {
  color: var(--danger);
}

.field-error {
  margin: 0;
  font-size: 12px;
  color: var(--danger);
}

input.invalid {
  border-color: var(--danger);
}

.target-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.target-row input {
  width: 110px;
  flex-shrink: 0;
}

.target-hint {
  white-space: nowrap;
}

.palette {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.swatch {
  width: 28px;
  height: 28px;
  padding: 0;
  border-radius: 50%;
  border: 2px solid transparent;
  box-shadow: var(--shadow-xs);
}

.swatch:hover {
  transform: scale(1.12);
}

.swatch.active {
  border-color: var(--text);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--text) 18%, transparent);
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

.actions-spacer {
  flex: 1;
}

@media (max-width: 720px) {
  .habits-grid {
    grid-template-columns: 1fr;
  }
  .habit-main {
    flex-direction: column;
    align-items: stretch;
  }
  .habit-actions {
    justify-content: flex-end;
  }
}
</style>
