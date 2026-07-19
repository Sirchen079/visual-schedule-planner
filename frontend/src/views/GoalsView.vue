<script setup>
// OKR 目标视图：数据自取自管（无 props/emits）。
// manual 类 KR 的 current_value 乐观更新（公式与后端一致：进度 = min(100, current/target)），
// 失败 toast 并静默重拉回退；增删改后整体静默刷新。
import { inject, onMounted, reactive, ref, watch } from 'vue'
import {
  createGoal,
  createKeyResult,
  deleteGoal,
  deleteKeyResult,
  listGoals,
  updateGoal,
  updateKeyResult,
} from '../api/goals'
import { listHabits } from '../api/habits'
import { listTags } from '../api/tasks'
import { askAssistant } from '../utils/assistant'
import ArtIcon from '../components/ArtIcon.vue'
import AppSpinner from '../components/ui/AppSpinner.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import PageHeader from '../components/ui/PageHeader.vue'
import SegmentedControl from '../components/ui/SegmentedControl.vue'

const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })
const confirmDialog = inject(
  'confirm-dialog',
  (o) => Promise.resolve(window.confirm(o.message || ''))
)

// 「问助手复盘」：把该目标的现状带进助手，由 AI 分析健康度并给下一步建议
function reviewGoal(goal) {
  const krs = (goal.key_results || [])
    .map((kr) => `「${kr.title}」${kr.current_value}/${kr.target_value}${kr.unit || ''}（${kr.progress}%）`)
    .join('、')
  askAssistant(
    `帮我复盘目标「${goal.title}」：当前总进度 ${goal.progress}%，关键结果：${krs || '暂无'}。` +
      '请分析进度是否健康（对照时间窗口）、最该优先推进哪个 KR、并把本周的具体安排落成任务。'
  )
}

const STATUS_META = {
  active: '进行中',
  done: '已完成',
  archived: '已归档',
}
const STATUS_OPTIONS = [
  { value: 'active', label: '进行中' },
  { value: 'done', label: '已完成' },
  { value: 'archived', label: '已归档' },
]
const KIND_META = {
  manual: { label: '手动', icon: 'task' },
  tag_task_count: { label: '任务', icon: 'tag' },
  habit_checkins: { label: '习惯', icon: 'steps' },
}
const KR_KIND_OPTIONS = [
  { value: 'manual', label: '手动累计' },
  { value: 'tag_task_count', label: '任务（标签）' },
  { value: 'habit_checkins', label: '习惯打卡' },
]

const goals = ref([])
const loading = ref(true)
// 自动类 KR 的关联选项；加载失败不阻塞目标列表
const tagOptions = ref([])
const habitOptions = ref([])

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    goals.value = await listGoals()
  } catch (e) {
    toast.error(`目标列表加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  listTags()
    .then((ts) => { tagOptions.value = ts })
    .catch(() => {})
  listHabits()
    .then((hs) => { habitOptions.value = hs })
    .catch(() => {})
})

// ---- 展示辅助 ----
function fmtNum(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '0'
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10)
}

function pct(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return 0
  return Math.min(100, Math.max(0, Math.round(v)))
}

function dateRange(g) {
  if (g.start_date && g.end_date) return `${g.start_date} ~ ${g.end_date}`
  if (g.start_date) return `自 ${g.start_date}`
  if (g.end_date) return `至 ${g.end_date}`
  return ''
}

function krLinkText(kr) {
  if (kr.kind === 'tag_task_count') {
    return kr.link?.tag ? `关联标签「${kr.link.tag}」` : '未关联标签'
  }
  if (kr.kind === 'habit_checkins') {
    const h = habitOptions.value.find((x) => x.id === Number(kr.link?.habit_id))
    return h ? `关联习惯「${h.name}」` : '关联习惯已删除'
  }
  return ''
}

// ---- 进度环（accent 色）----
const RING_R = 26
const RING_C = +(2 * Math.PI * RING_R).toFixed(2)
function ringOffset(p) {
  return RING_C * (1 - pct(p) / 100)
}

// ---- manual KR 数值：乐观更新，公式与后端一致；成功后用响应对齐，失败回退 ----
function krPct(kr) {
  const target = Number(kr.target_value) || 1
  return Math.min(100, Math.round(((Number(kr.current_value) || 0) / target) * 100))
}

function refreshGoalProgress(goalId) {
  const g = goals.value.find((x) => x.id === goalId)
  if (!g) return
  if (!g.key_results.length) {
    g.progress = 0
    return
  }
  g.progress = Math.round(g.key_results.reduce((s, kr) => s + pct(kr.progress), 0) / g.key_results.length)
}

function applyKr(updated) {
  const g = goals.value.find((x) => x.id === updated.goal_id)
  if (!g) return
  const i = g.key_results.findIndex((kr) => kr.id === updated.id)
  if (i !== -1) g.key_results[i] = updated
  refreshGoalProgress(updated.goal_id)
}

async function saveKrValue(kr, value) {
  kr.current_value = value
  kr.progress = krPct(kr)
  refreshGoalProgress(kr.goal_id)
  try {
    applyKr(await updateKeyResult(kr.id, { current_value: value }))
  } catch (e) {
    toast.error(`更新进度失败：${e.message}`)
    await load(true)
  }
}

function stepKr(kr, delta) {
  const next = Math.max(0, (Number(kr.current_value) || 0) + delta)
  if (next === Number(kr.current_value)) return
  saveKrValue(kr, next)
}

// 输入框失焦 / 回车（change 事件）提交；非法输入回显原值
function commitKrValue(kr, event) {
  const raw = String(event.target.value).trim()
  const v = Number(raw)
  if (raw === '' || !Number.isFinite(v) || v < 0) {
    event.target.value = fmtNum(kr.current_value)
    return
  }
  if (v === Number(kr.current_value)) return
  saveKrValue(kr, v)
}

async function removeKr(kr) {
  const ok = await confirmDialog({
    title: '删除关键结果',
    message: `关键结果「${kr.title}」将被删除。`,
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteKeyResult(kr.id)
    toast.success(`已删除「${kr.title}」`)
    await load(true)
  } catch (e) {
    toast.error(`删除失败：${e.message}`)
  }
}

// ---- 关联选择：类型切换后清空已选关联，避免串类型 ----
function buildLink(kind, tag, habitId) {
  if (kind === 'tag_task_count') return { tag }
  if (kind === 'habit_checkins') return { habit_id: Number(habitId) }
  return {}
}

function validTarget(v) {
  const n = Number(v)
  return Number.isFinite(n) && n > 0 ? n : 1
}

function linkError(kind, tag, habitId) {
  if (kind === 'tag_task_count' && !tag) return '请选择关联的标签'
  if (kind === 'habit_checkins' && !habitId) return '请选择关联的习惯'
  return ''
}

// ---- 新建 / 编辑目标弹窗 ----
const goalModalOpen = ref(false)
const editingGoal = ref(null)
const goalSaving = ref(false)
const goalFormError = ref('')
const goalForm = reactive({ title: '', notes: '', start_date: '', end_date: '', status: 'active' })
const krDrafts = ref([])

function blankDraft() {
  return { title: '', kind: 'manual', target_value: 1, unit: '', tag: '', habit_id: '' }
}

function addKrDraft() {
  krDrafts.value.push(blankDraft())
}

function removeKrDraft(i) {
  krDrafts.value.splice(i, 1)
}

function openCreateGoal() {
  editingGoal.value = null
  Object.assign(goalForm, { title: '', notes: '', start_date: '', end_date: '', status: 'active' })
  krDrafts.value = [blankDraft()]
  goalFormError.value = ''
  goalModalOpen.value = true
}

function openEditGoal(g) {
  editingGoal.value = g
  Object.assign(goalForm, {
    title: g.title,
    notes: g.notes || '',
    start_date: g.start_date || '',
    end_date: g.end_date || '',
    status: g.status,
  })
  goalFormError.value = ''
  goalModalOpen.value = true
}

function closeGoalModal() {
  goalModalOpen.value = false
  editingGoal.value = null
}

async function saveGoal() {
  const title = goalForm.title.trim()
  if (!title) {
    goalFormError.value = '请填写目标标题'
    return
  }
  if (goalForm.start_date && goalForm.end_date && goalForm.end_date < goalForm.start_date) {
    goalFormError.value = '结束日期不能早于开始日期'
    return
  }
  goalSaving.value = true
  try {
    if (editingGoal.value) {
      await updateGoal(editingGoal.value.id, {
        title,
        notes: goalForm.notes.trim(),
        status: goalForm.status,
        start_date: goalForm.start_date || null,
        end_date: goalForm.end_date || null,
      })
      toast.success(`已保存「${title}」`)
    } else {
      const keyResults = []
      for (const d of krDrafts.value) {
        if (!d.title.trim()) {
          goalFormError.value = '关键结果需要填写标题'
          goalSaving.value = false
          return
        }
        const err = linkError(d.kind, d.tag, d.habit_id)
        if (err) {
          goalFormError.value = err
          goalSaving.value = false
          return
        }
        keyResults.push({
          title: d.title.trim(),
          kind: d.kind,
          target_value: validTarget(d.target_value),
          unit: d.unit.trim(),
          link: buildLink(d.kind, d.tag, d.habit_id),
        })
      }
      const payload = { title, notes: goalForm.notes.trim(), key_results: keyResults }
      if (goalForm.start_date) payload.start_date = goalForm.start_date
      if (goalForm.end_date) payload.end_date = goalForm.end_date
      await createGoal(payload)
      toast.success(`已创建「${title}」`)
    }
    closeGoalModal()
    await load(true)
  } catch (e) {
    toast.error(`保存失败：${e.message}`)
  } finally {
    goalSaving.value = false
  }
}

async function removeGoal() {
  const g = editingGoal.value
  if (!g) return
  const ok = await confirmDialog({
    title: '删除目标',
    message: `「${g.title}」与其关键结果将被删除。`,
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteGoal(g.id)
    toast.success(`已删除「${g.title}」`)
    closeGoalModal()
    await load(true)
  } catch (e) {
    toast.error(`删除失败：${e.message}`)
  }
}

// ---- 添加 / 编辑关键结果弹窗 ----
const krModalOpen = ref(false)
const krEditing = ref(null)
const krGoalId = ref(null)
const krSaving = ref(false)
const krFormError = ref('')
const krForm = reactive({ title: '', kind: 'manual', target_value: 1, unit: '', tag: '', habit_id: '' })

watch(
  () => krForm.kind,
  () => {
    krForm.tag = ''
    krForm.habit_id = ''
  }
)

function openCreateKr(g) {
  krEditing.value = null
  krGoalId.value = g.id
  Object.assign(krForm, { title: '', kind: 'manual', target_value: 1, unit: '', tag: '', habit_id: '' })
  krFormError.value = ''
  krModalOpen.value = true
}

function openEditKr(g, kr) {
  krEditing.value = kr
  krGoalId.value = g.id
  Object.assign(krForm, {
    title: kr.title,
    kind: kr.kind,
    target_value: kr.target_value,
    unit: kr.unit || '',
    tag: kr.link?.tag || '',
    habit_id: kr.link?.habit_id ? String(kr.link.habit_id) : '',
  })
  krFormError.value = ''
  krModalOpen.value = true
}

function closeKrModal() {
  krModalOpen.value = false
  krEditing.value = null
}

async function saveKr() {
  const title = krForm.title.trim()
  if (!title) {
    krFormError.value = '请填写关键结果标题'
    return
  }
  if (!(Number(krForm.target_value) > 0)) {
    krFormError.value = '目标值需大于 0'
    return
  }
  const err = linkError(krForm.kind, krForm.tag, krForm.habit_id)
  if (err) {
    krFormError.value = err
    return
  }
  const payload = {
    title,
    kind: krForm.kind,
    target_value: Number(krForm.target_value),
    unit: krForm.unit.trim(),
    link: buildLink(krForm.kind, krForm.tag, krForm.habit_id),
  }
  krSaving.value = true
  try {
    if (krEditing.value) {
      await updateKeyResult(krEditing.value.id, payload)
    } else {
      await createKeyResult(krGoalId.value, payload)
    }
    toast.success(`已保存「${title}」`)
    closeKrModal()
    await load(true)
  } catch (e) {
    toast.error(`保存失败：${e.message}`)
  } finally {
    krSaving.value = false
  }
}
</script>

<template>
  <div class="goals workspace-page">
    <PageHeader icon="flag" title="目标" subtitle="方向对了，每一步都算数。">
      <template #actions>
        <button class="create-btn" @click="openCreateGoal">
          <ArtIcon name="plus" tone="on-accent" :size="20" />
          <span>新建目标</span>
        </button>
      </template>
    </PageHeader>

    <div v-if="loading" class="loading-wrap">
      <AppSpinner label="加载目标" />
    </div>

    <EmptyState
      v-else-if="!goals.length"
      icon="flag"
      title="还没有目标"
      hint="定一个季度目标，让每天的忙碌有方向。"
    >
      <button type="button" class="empty-create" @click="openCreateGoal">
        <ArtIcon name="plus" tone="on-accent" :size="16" />
        <span>新建目标</span>
      </button>
    </EmptyState>

    <div v-else class="goals-grid">
      <article
        v-for="(g, i) in goals"
        :key="g.id"
        class="goal-card section-panel animate-in"
        :class="{ archived: g.status === 'archived' }"
        :style="{ animationDelay: `${i * 0.05}s` }"
      >
        <div class="goal-inner">
          <div class="goal-head">
            <div class="goal-title">
              <h3>{{ g.title }}</h3>
              <p v-if="dateRange(g)" class="muted">{{ dateRange(g) }}</p>
            </div>
            <span class="status-badge" :class="`st-${g.status}`">
              {{ STATUS_META[g.status] || g.status }}
            </span>
          </div>

          <p v-if="g.notes" class="goal-notes muted">{{ g.notes }}</p>

          <div class="goal-progress">
            <div class="ring-wrap" role="img" :aria-label="`总进度 ${pct(g.progress)}%`">
              <svg class="ring" viewBox="0 0 64 64" focusable="false">
                <circle class="ring-track" cx="32" cy="32" :r="RING_R" />
                <circle
                  class="ring-fill"
                  cx="32"
                  cy="32"
                  :r="RING_R"
                  :stroke-dasharray="RING_C"
                  :stroke-dashoffset="ringOffset(g.progress)"
                />
              </svg>
              <span class="ring-text">{{ pct(g.progress) }}%</span>
            </div>
            <div class="goal-progress-main">
              <span class="progress-text">
                总进度 · {{ g.key_results.length }} 个关键结果
              </span>
              <div class="progress-track">
                <div class="progress-fill" :style="{ width: `${pct(g.progress)}%` }"></div>
              </div>
            </div>
          </div>

          <div v-if="g.key_results.length" class="kr-list">
            <div v-for="kr in g.key_results" :key="kr.id" class="kr-row">
              <div class="kr-line">
                <span class="kr-kind">
                  <ArtIcon :name="KIND_META[kr.kind]?.icon || 'task'" tone="aqua" :size="12" />
                  <span>{{ KIND_META[kr.kind]?.label || kr.kind }}</span>
                </span>
                <span class="kr-title" :title="kr.title">{{ kr.title }}</span>
                <span v-if="kr.kind !== 'manual'" class="kr-value">
                  {{ fmtNum(kr.current_value) }}/{{ fmtNum(kr.target_value) }}{{ kr.unit ? ` ${kr.unit}` : '' }}
                </span>
                <span v-else class="kr-stepper">
                  <button
                    type="button"
                    class="ghost step-btn"
                    aria-label="减少数值"
                    @click="stepKr(kr, -1)"
                  >
                    −
                  </button>
                  <input
                    class="val-input"
                    type="number"
                    min="0"
                    :value="fmtNum(kr.current_value)"
                    :aria-label="`${kr.title} 当前数值`"
                    @change="commitKrValue(kr, $event)"
                    @keydown.enter.prevent="(e) => e.target.blur()"
                  />
                  <button
                    type="button"
                    class="ghost step-btn"
                    aria-label="增加数值"
                    @click="stepKr(kr, 1)"
                  >
                    +
                  </button>
                  <span class="kr-value">/{{ fmtNum(kr.target_value) }}{{ kr.unit ? ` ${kr.unit}` : '' }}</span>
                </span>
                <span class="kr-ops">
                  <button type="button" class="ghost mini-btn" @click="openEditKr(g, kr)">编辑</button>
                  <button type="button" class="ghost mini-btn" @click="removeKr(kr)">删除</button>
                </span>
              </div>
              <div class="kr-sub">
                <div class="kr-track">
                  <div class="kr-fill" :style="{ width: `${pct(kr.progress)}%` }"></div>
                </div>
                <span class="kr-pct">{{ pct(kr.progress) }}%</span>
              </div>
              <p v-if="krLinkText(kr)" class="kr-link muted">{{ krLinkText(kr) }} · 数值自动统计</p>
            </div>
          </div>

          <div class="goal-foot">
            <button type="button" class="ghost add-kr-btn" @click="openCreateKr(g)">
              <ArtIcon name="plus" tone="pearl" :size="14" />
              <span>添加关键结果</span>
            </button>
            <span class="actions-spacer"></span>
            <button type="button" class="ghost mini-btn" @click="reviewGoal(g)">问助手复盘</button>
            <button type="button" class="ghost mini-btn" @click="openEditGoal(g)">编辑目标</button>
          </div>
        </div>
      </article>
    </div>

    <BaseModal
      :open="goalModalOpen"
      size="md"
      :label="editingGoal ? '编辑目标' : '新建目标'"
      @close="closeGoalModal"
    >
      <div class="goal-modal">
        <div class="modal-head">
          <div class="modal-title">{{ editingGoal ? '编辑目标' : '新建目标' }}</div>
        </div>
        <form class="goal-form" @submit.prevent="saveGoal">
          <div class="field">
            <label>标题 <span class="required">*</span></label>
            <input
              v-model="goalForm.title"
              placeholder="如：三季度完成书稿初稿"
              data-autofocus
              :class="{ invalid: goalFormError }"
            />
            <p v-if="goalFormError" class="field-error">{{ goalFormError }}</p>
          </div>

          <div class="field-row">
            <div class="field">
              <label>开始日期</label>
              <input v-model="goalForm.start_date" type="date" />
            </div>
            <div class="field">
              <label>结束日期</label>
              <input v-model="goalForm.end_date" type="date" />
            </div>
          </div>

          <div v-if="editingGoal" class="field">
            <label>状态</label>
            <SegmentedControl v-model="goalForm.status" :options="STATUS_OPTIONS" size="sm" />
          </div>

          <div class="field">
            <label>备注</label>
            <textarea v-model="goalForm.notes" rows="2" placeholder="为什么是这个目标…"></textarea>
          </div>

          <div v-if="!editingGoal" class="field">
            <label>
              关键结果
              <span class="muted label-hint">（可选，保存后也可随时添加）</span>
            </label>
            <div class="kr-drafts">
              <div v-for="(d, i) in krDrafts" :key="i" class="kr-draft">
                <div class="kr-draft-main">
                  <input v-model="d.title" placeholder="如：写完 3 万字" :aria-label="`关键结果 ${i + 1} 标题`" />
                  <select v-model="d.kind" :aria-label="`关键结果 ${i + 1} 类型`">
                    <option value="manual">手动</option>
                    <option value="tag_task_count">任务（标签）</option>
                    <option value="habit_checkins">习惯打卡</option>
                  </select>
                  <button
                    type="button"
                    class="ghost icon-btn"
                    :aria-label="`移除关键结果 ${i + 1}`"
                    @click="removeKrDraft(i)"
                  >
                    <ArtIcon name="close" tone="pearl" :size="14" />
                  </button>
                </div>
                <div class="kr-draft-sub">
                  <input
                    v-model.number="d.target_value"
                    type="number"
                    min="1"
                    placeholder="目标值"
                    :aria-label="`关键结果 ${i + 1} 目标值`"
                  />
                  <input
                    v-model="d.unit"
                    placeholder="单位（如 词 / 个 / 次）"
                    :aria-label="`关键结果 ${i + 1} 单位`"
                  />
                  <select
                    v-if="d.kind === 'tag_task_count'"
                    v-model="d.tag"
                    :aria-label="`关键结果 ${i + 1} 关联标签`"
                  >
                    <option value="" disabled>选择标签</option>
                    <option v-for="t in tagOptions" :key="t.id" :value="t.name">{{ t.name }}</option>
                  </select>
                  <select
                    v-else-if="d.kind === 'habit_checkins'"
                    v-model="d.habit_id"
                    :aria-label="`关键结果 ${i + 1} 关联习惯`"
                  >
                    <option value="" disabled>选择习惯</option>
                    <option v-for="h in habitOptions" :key="h.id" :value="String(h.id)">{{ h.name }}</option>
                  </select>
                </div>
              </div>
              <button type="button" class="ghost add-row-btn" @click="addKrDraft">
                <ArtIcon name="plus" tone="pearl" :size="14" />
                <span>再加一个关键结果</span>
              </button>
            </div>
          </div>

          <div class="actions">
            <button v-if="editingGoal" type="button" class="danger" @click="removeGoal">删除</button>
            <span class="actions-spacer"></span>
            <button type="button" class="ghost" @click="closeGoalModal">取消</button>
            <button type="submit" :disabled="goalSaving">{{ goalSaving ? '保存中…' : '保存' }}</button>
          </div>
        </form>
      </div>
    </BaseModal>

    <BaseModal
      :open="krModalOpen"
      size="sm"
      :label="krEditing ? '编辑关键结果' : '添加关键结果'"
      @close="closeKrModal"
    >
      <div class="goal-modal">
        <div class="modal-head">
          <div class="modal-title">{{ krEditing ? '编辑关键结果' : '添加关键结果' }}</div>
        </div>
        <form class="goal-form" @submit.prevent="saveKr">
          <div class="field">
            <label>标题 <span class="required">*</span></label>
            <input
              v-model="krForm.title"
              placeholder="如：完成 20 个重构任务"
              data-autofocus
              :class="{ invalid: krFormError }"
            />
            <p v-if="krFormError" class="field-error">{{ krFormError }}</p>
          </div>

          <div class="field">
            <label>类型</label>
            <SegmentedControl v-model="krForm.kind" :options="KR_KIND_OPTIONS" size="sm" />
          </div>

          <div v-if="krForm.kind === 'tag_task_count'" class="field">
            <label>关联标签</label>
            <select v-model="krForm.tag">
              <option value="" disabled>选择标签</option>
              <option v-for="t in tagOptions" :key="t.id" :value="t.name">{{ t.name }}</option>
            </select>
            <p class="muted field-hint">统计目标周期内带该标签的已完成任务数</p>
          </div>

          <div v-else-if="krForm.kind === 'habit_checkins'" class="field">
            <label>关联习惯</label>
            <select v-model="krForm.habit_id">
              <option value="" disabled>选择习惯</option>
              <option v-for="h in habitOptions" :key="h.id" :value="String(h.id)">{{ h.name }}</option>
            </select>
            <p class="muted field-hint">统计目标周期内该习惯的打卡总次数</p>
          </div>

          <div class="field-row">
            <div class="field">
              <label>目标值 <span class="required">*</span></label>
              <input v-model.number="krForm.target_value" type="number" min="1" />
            </div>
            <div class="field">
              <label>单位</label>
              <input v-model="krForm.unit" placeholder="如 个 / 词 / 次" />
            </div>
          </div>

          <p v-if="krForm.kind !== 'manual'" class="muted field-hint">
            自动统计的数值由后端按关联数据实时计算，无需手动更新。
          </p>

          <div class="actions">
            <span class="actions-spacer"></span>
            <button type="button" class="ghost" @click="closeKrModal">取消</button>
            <button type="submit" :disabled="krSaving">{{ krSaving ? '保存中…' : '保存' }}</button>
          </div>
        </form>
      </div>
    </BaseModal>
  </div>
</template>

<style scoped>
.goals {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 根节点已有 gap，去掉 PageHeader 自带下间距避免叠加 */
.goals :deep(.page-header) {
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

.goals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(430px, 100%), 1fr));
  gap: 16px;
  align-items: start;
}

.goal-card {
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, opacity 0.2s ease;
}

.goal-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
  border-color: var(--border-strong);
}

.goal-card.archived {
  opacity: 0.6;
}

.goal-inner {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}

.goal-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.goal-title {
  min-width: 0;
  flex: 1;
}

.goal-title h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.goal-title p {
  margin: 3px 0 0;
}

.status-badge {
  flex-shrink: 0;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 650;
  white-space: nowrap;
}

.status-badge.st-active {
  color: var(--accent-strong);
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 24%, transparent);
}

.status-badge.st-done {
  color: var(--success);
  background: color-mix(in srgb, var(--success) 14%, transparent);
  border-color: color-mix(in srgb, var(--success) 30%, transparent);
}

.status-badge.st-archived {
  color: var(--text-soft);
  background: var(--surface-2);
  border-color: var(--border);
}

.goal-notes {
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.goal-progress {
  display: flex;
  align-items: center;
  gap: 14px;
}

.ring-wrap {
  position: relative;
  flex-shrink: 0;
  width: 64px;
  height: 64px;
}

.ring {
  width: 64px;
  height: 64px;
  transform: rotate(-90deg);
}

.ring circle {
  fill: none;
  stroke-width: 6;
  stroke-linecap: round;
}

.ring-track {
  stroke: var(--surface-3);
}

.ring-fill {
  stroke: var(--accent);
  transition: stroke-dashoffset 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.ring-text {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 800;
  color: var(--text);
}

.goal-progress-main {
  flex: 1;
  min-width: 0;
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
  background: var(--btn-gradient);
  transition: width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* ---- 关键结果列表 ---- */
.kr-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.kr-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kr-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}

.kr-kind {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-strong);
  background: var(--accent-soft);
  border: 1px solid color-mix(in srgb, var(--accent) 20%, transparent);
}

.kr-title {
  flex: 1;
  min-width: 100px;
  font-size: 13px;
  font-weight: 650;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kr-value {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 650;
  color: var(--text-soft);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.kr-stepper {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.step-btn {
  width: 24px;
  height: 24px;
  min-width: 24px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  line-height: 1;
  border-radius: var(--radius-xs);
}

.val-input {
  width: 62px;
  padding: 3px 4px;
  text-align: center;
  font-size: 12px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  border-radius: var(--radius-xs);
}

/* 行内步进已有 - / + 按钮，隐藏数字输入自带箭头 */
.val-input::-webkit-outer-spin-button,
.val-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.val-input {
  appearance: textfield;
  -moz-appearance: textfield;
}

.kr-ops {
  flex-shrink: 0;
  display: inline-flex;
  gap: 4px;
}

.mini-btn {
  padding: 4px 9px;
  font-size: 12px;
  border-radius: var(--radius-xs);
}

.kr-sub {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kr-track {
  flex: 1;
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  overflow: hidden;
}

.kr-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--btn-gradient);
  transition: width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.kr-pct {
  flex-shrink: 0;
  min-width: 34px;
  text-align: right;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-soft);
  font-variant-numeric: tabular-nums;
}

.kr-link {
  margin: 0;
  font-size: 12px;
}

.goal-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.add-kr-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  font-size: 12px;
  border-radius: var(--radius-xs);
}

/* ---- 弹窗 ---- */
.goal-modal {
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

.goal-form {
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

.label-hint {
  font-weight: 400;
  font-size: 12px;
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.required {
  color: var(--danger);
}

.field-error {
  margin: 0;
  font-size: 12px;
  color: var(--danger);
}

.field-hint {
  margin: 0;
  font-size: 12px;
}

input.invalid {
  border-color: var(--danger);
}

.kr-drafts {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.kr-draft {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.kr-draft-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 128px 32px;
  gap: 8px;
  align-items: center;
}

.kr-draft-sub {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
}

.icon-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-xs);
}

.add-row-btn {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  font-size: 12px;
  border-radius: var(--radius-xs);
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
  .goals-grid {
    grid-template-columns: 1fr;
  }
  .field-row {
    grid-template-columns: 1fr;
  }
  .kr-draft-main {
    grid-template-columns: minmax(0, 1fr) 32px;
  }
  .kr-draft-main select {
    grid-column: 1 / -1;
  }
  .kr-draft-sub {
    grid-template-columns: 1fr 1fr;
  }
  .kr-draft-sub select {
    grid-column: 1 / -1;
  }
}
</style>
