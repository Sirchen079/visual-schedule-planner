<script setup lang="ts">
/**
 * 目标（OKR）视图（/goals）：目标卡 + 关键结果进度条 + 进度登记，B×C 暗色。
 * - 进度百分比本地推导（current/target，纯函数 krPercent/goalPercent 可单测）；
 *   KR 进度登记走 PATCH（乐观更新 + 失败回滚，约束①）
 * - 新建目标 / 添加关键结果 / 删除 KR / 归档目标 / 删除目标，全部走真实 API
 * - run done 后由壳层自动刷新（App.vue 接线，覆盖 AI update_goal/update_kr_progress）
 */
import { computed, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import DomainState from '../components/domain/DomainState.vue'
import { GOAL_STATUS_LABELS, goalPercent, krPercent, useGoalsStore } from '../stores/goals'
import type { KeyResult } from '../api/goals'

const goals = useGoalsStore()

/* ---- 新建目标 ---- */
const creating = ref(false)
const goalTitle = ref('')
const goalNotes = ref('')
const goalRange = ref('')
const submittingGoal = ref(false)

async function submitGoal(): Promise<void> {
  const t = goalTitle.value.trim()
  if (!t || submittingGoal.value) return
  submittingGoal.value = true
  const ok = await goals.create({
    title: t,
    notes: goalNotes.value.trim() || undefined,
    start_date: goalRange.value || null,
  })
  submittingGoal.value = false
  if (ok) {
    goalTitle.value = ''
    goalNotes.value = ''
    goalRange.value = ''
    creating.value = false
  }
}

/* ---- 添加 KR（每目标一张内联表单） ---- */
const krFormFor = ref<number | null>(null)
const krTitle = ref('')
const krTarget = ref<number>(100)
const krUnit = ref('')
const submittingKr = ref(false)

function openKrForm(goalId: number): void {
  krFormFor.value = goalId
  krTitle.value = ''
  krTarget.value = 100
  krUnit.value = ''
}

async function submitKr(goalId: number): Promise<void> {
  const t = krTitle.value.trim()
  if (!t || submittingKr.value) return
  submittingKr.value = true
  const ok = await goals.addKeyResult(goalId, { title: t, target_value: krTarget.value, unit: krUnit.value.trim() })
  submittingKr.value = false
  if (ok) krFormFor.value = null
}

/** KR 进度快捷登记：直接改数字输入，change 即提交（乐观更新） */
function onKrInput(kr: KeyResult, ev: Event): void {
  const v = Number((ev.target as HTMLInputElement).value)
  if (Number.isFinite(v) && v !== kr.current_value) void goals.updateKrProgress(kr.id, v)
}

const activeGoals = computed(() => (goals.items ?? []).filter((g) => g.status !== 'archived'))

onMounted(() => {
  if (goals.items === null) void goals.load()
})
</script>

<template>
  <section class="goals-view">
    <Teleport defer to="#head-actions">
      <button class="new-btn" @click="creating = !creating">
        <AppIcon name="plus" :size="14" />
        {{ creating ? '收起' : '新建目标' }}
      </button>
    </Teleport>

    <header class="gv-head">
      <span class="gv-caption">目标与关键结果</span>
      <span v-if="activeGoals.length > 0" class="gv-note">
        {{ activeGoals.length }} 个进行中的目标
        <template v-if="goals.lastRefreshedAt"> · AI 写操作后自动刷新</template>
      </span>
    </header>

    <div v-if="goals.actionError" class="action-error" role="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ goals.actionError }}</span>
    </div>

    <form v-if="creating" class="creator" @submit.prevent="submitGoal">
      <input v-model="goalTitle" class="in t-in" placeholder="目标标题（必填，如：学期不挂科）" aria-label="目标标题" />
      <input v-model="goalRange" class="in r-in" type="date" aria-label="开始日期（可选）" />
      <input v-model="goalNotes" class="in n-in" placeholder="备注（可选）" aria-label="目标备注" />
      <button class="submit" type="submit" :disabled="!goalTitle.trim() || submittingGoal">
        {{ submittingGoal ? '创建中…' : '创建' }}
      </button>
    </form>

    <DomainState
      :loading="goals.loading && goals.items === null"
      loading-text="正在拉取目标…"
      :error="goals.error"
      :empty="!goals.loading && goals.items !== null && goals.items.length === 0"
      empty-title="还没有立目标"
      @retry="goals.load()"
    >
      目标管方向，关键结果管刻度。先立一个目标，再给它配上<br />可度量的关键结果——进度条会随每次登记往前走。
    </DomainState>

    <div v-if="activeGoals.length > 0" class="cards">
      <article v-for="g in activeGoals" :key="g.id" class="goal-card">
        <header class="gc-head">
          <div class="gc-title-block">
            <span class="gc-title">{{ g.title }}</span>
            <span class="gc-status">{{ GOAL_STATUS_LABELS[g.status] ?? g.status }}</span>
            <span v-if="g.start_date || g.end_date" class="gc-range">
              {{ g.start_date ?? '…' }} → {{ g.end_date ?? '…' }}
            </span>
          </div>
          <div class="gc-actions">
            <button class="mini" @click="openKrForm(g.id)">
              <AppIcon name="plus" :size="12" /> 关键结果
            </button>
            <button class="mini" @click="goals.archive(g.id)">归档</button>
            <button class="mini danger" aria-label="删除目标" @click="goals.remove(g.id)">
              <AppIcon name="x" :size="12" />
            </button>
          </div>
        </header>

        <p v-if="g.notes" class="gc-notes">{{ g.notes }}</p>

        <!-- 整体进度 -->
        <div class="gc-overall">
          <div class="bar big">
            <div class="fill" :style="{ width: `${goalPercent(g) ?? 0}%` }" />
          </div>
          <span class="pct">{{ goalPercent(g) === null ? '未设 KR' : `${goalPercent(g)}%` }}</span>
        </div>

        <!-- KR 列表 -->
        <ul v-if="g.key_results.length > 0" class="krs">
          <li v-for="kr in g.key_results" :key="kr.id" class="kr">
            <span class="kr-title">{{ kr.title }}</span>
            <div class="kr-mid">
              <div class="bar">
                <div class="fill" :style="{ width: `${krPercent(kr)}%` }" />
              </div>
              <span class="pct small">{{ krPercent(kr) }}%</span>
            </div>
            <label class="kr-input">
              <input
                type="number"
                :value="kr.current_value"
                :disabled="goals.pendingKrs.includes(kr.id)"
                :aria-label="`更新 ${kr.title} 当前进度`"
                @change="onKrInput(kr, $event)"
              />
              <span class="kr-unit">/ {{ kr.target_value }} {{ kr.unit }}</span>
            </label>
            <button class="mini danger" :aria-label="`删除关键结果 ${kr.title}`" @click="goals.removeKeyResult(kr.id)">
              <AppIcon name="x" :size="12" />
            </button>
          </li>
        </ul>
        <p v-else class="gc-nokr">还没有关键结果 —— 目标要配可度量的刻度才知道走没走到。</p>

        <!-- KR 内联表单 -->
        <form v-if="krFormFor === g.id" class="kr-form" @submit.prevent="submitKr(g.id)">
          <input v-model="krTitle" class="in kt-in" placeholder="关键结果（必填，如：专业课均分 85）" aria-label="关键结果标题" />
          <input v-model.number="krTarget" class="in kn-in" type="number" min="1" aria-label="目标值" />
          <input v-model="krUnit" class="in ku-in" placeholder="单位" aria-label="单位" />
          <button class="submit" type="submit" :disabled="!krTitle.trim() || submittingKr">
            {{ submittingKr ? '添加中…' : '添加' }}
          </button>
        </form>
      </article>
    </div>
  </section>
</template>

<style scoped>
.goals-view {
  flex: 1;
  min-height: 0;
  padding: 18px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: auto;
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

.gv-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.gv-caption {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.gv-note {
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

.creator,
.kr-form {
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
  color-scheme: dark;
}
.in::placeholder {
  color: var(--ink-faint);
}
.in:focus {
  outline: none;
  border-color: var(--line-hover);
}
.t-in,
.kt-in {
  flex: 1;
  min-width: 160px;
}
.n-in {
  flex: 1;
  min-width: 120px;
}
.r-in {
  width: 150px;
}
.kn-in {
  width: 84px;
}
.ku-in {
  width: 76px;
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

.cards {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.goal-card {
  border: 1px solid var(--line-2);
  background: var(--bg-raise);
  border-radius: var(--radius-m);
  padding: 15px 17px;
  display: flex;
  flex-direction: column;
  gap: 11px;
}
.gc-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.gc-title-block {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 9px;
  flex-wrap: wrap;
}
.gc-title {
  font-family: var(--serif);
  font-size: 16.5px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: var(--ink);
}
.gc-status {
  font-size: 11px;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border-weak);
  border-radius: var(--radius-pill);
  padding: 0 8px;
}
.gc-range {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}
.gc-actions {
  display: flex;
  gap: 6px;
  flex: none;
}
.mini {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 9px;
}
.mini:hover {
  border-color: var(--line-hover);
  color: var(--amber-soft);
}
.mini.danger:hover {
  color: var(--terra-soft);
  border-color: var(--terra-dashed);
}
.gc-notes {
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.6;
}

.gc-overall {
  display: flex;
  align-items: center;
  gap: 10px;
}
.bar {
  flex: 1;
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--bg-sink);
  border: 1px solid var(--line);
  overflow: hidden;
}
.bar.big {
  height: 9px;
}
.fill {
  height: 100%;
  background: var(--amber-dim);
  border-radius: var(--radius-pill);
  transition: width 0.25s ease;
}
.pct {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  color: var(--amber-soft);
  width: 62px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  flex: none;
}
.pct.small {
  font-size: 12px;
  color: var(--ink-2);
  width: 40px;
}

.krs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-top: 1px solid var(--line);
  padding-top: 10px;
}
.kr {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) minmax(160px, 2fr) 168px auto;
  gap: 12px;
  align-items: center;
}
.kr-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.4;
  word-break: break-word;
}
.kr-mid {
  display: flex;
  align-items: center;
  gap: 8px;
}
.kr-input {
  display: flex;
  align-items: baseline;
  gap: 5px;
}
.kr-input input {
  width: 76px;
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink);
  background: var(--bg-sink);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 4px 8px;
  color-scheme: dark;
}
.kr-input input:focus {
  outline: none;
  border-color: var(--amber-border);
}
.kr-input input:disabled {
  opacity: 0.5;
}
.kr-unit {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}
.gc-nokr {
  font-size: 12px;
  color: var(--ink-3);
  font-style: italic;
  border-top: 1px solid var(--line);
  padding-top: 10px;
}
</style>
