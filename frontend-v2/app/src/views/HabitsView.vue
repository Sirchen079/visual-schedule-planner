<script setup lang="ts">
/**
 * 习惯视图（/habits）：习惯卡 + 今日打卡 + 连续天数 + 近 14 天打卡带。
 * - 打卡/撤销走 API（乐观更新 + 失败回滚，回滚消息行内可见）
 * - 打卡带：GET /api/habits/{id}/logs?days=14 懒加载；方块深浅按当日打卡次数
 * - 新建习惯：名称必填，周期/目标次数可选；删除为软删除
 * - run done 后由壳层自动刷新（App.vue 接线，覆盖 AI check_in_habit 等写操作）
 */
import { computed, onMounted, ref, watch } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import DomainState from '../components/domain/DomainState.vue'
import { recentDays, useHabitsStore } from '../stores/habits'
import type { HabitPeriod } from '../api/habits'
import { toIsoDate } from '../utils/date'

const habits = useHabitsStore()
const todayIso = toIsoDate(new Date())
const stripDays = computed(() => recentDays(todayIso, 14))

const PERIOD_LABEL: Record<HabitPeriod, string> = { daily: '每日', weekly: '每周' }

/** 打卡带方块强度：0 未打卡；1..target 逐级加深；达标最深 */
function dotClass(habitId: number, date: string): string {
  const habit = habits.items?.find((h) => h.id === habitId)
  const count = habits.logsByHabit[habitId]?.[date] ?? 0
  if (count <= 0) return 'none'
  const target = habit?.target_count ?? 1
  if (date === todayIso && habit?.status.done_today) return 'full'
  return count >= target ? 'full' : 'part'
}

/* ---- 新建习惯 ---- */
const creating = ref(false)
const name = ref('')
const period = ref<HabitPeriod>('daily')
const targetCount = ref(1)
const submitting = ref(false)

async function submit(): Promise<void> {
  const n = name.value.trim()
  if (!n || submitting.value) return
  submitting.value = true
  const ok = await habits.create({ name: n, period: period.value, target_count: targetCount.value })
  submitting.value = false
  if (ok) {
    name.value = ''
    period.value = 'daily'
    targetCount.value = 1
    creating.value = false
  }
}

/** 新习惯进场后补拉打卡带 */
watch(
  () => habits.items?.map((h) => h.id).join(',') ?? '',
  (ids) => {
    for (const id of ids.split(',').filter(Boolean).map(Number)) {
      if (habits.logsByHabit[id] === undefined) void habits.loadLogs(id)
    }
  },
)

onMounted(() => {
  if (habits.items === null) void habits.load()
})
</script>

<template>
  <section class="habits-view">
    <Teleport defer to="#head-actions">
      <button class="new-btn" @click="creating = !creating">
        <AppIcon name="plus" :size="14" />
        {{ creating ? '收起' : '新建习惯' }}
      </button>
    </Teleport>

    <header class="hv-head">
      <span class="hv-caption">今日打卡</span>
      <span class="hv-date">{{ todayIso }}</span>
      <span v-if="habits.items && habits.items.length > 0" class="hv-note">
        {{ habits.items.filter((h) => h.status.done_today).length }}/{{ habits.items.length }} 已完成
        <template v-if="habits.lastRefreshedAt"> · AI 写操作后自动刷新</template>
      </span>
    </header>

    <div v-if="habits.actionError" class="action-error" role="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ habits.actionError }}</span>
    </div>

    <form v-if="creating" class="creator" @submit.prevent="submit">
      <input v-model="name" class="in name-in" placeholder="习惯名称（必填，如：晨读英语）" aria-label="习惯名称" />
      <select v-model="period" class="in" aria-label="打卡周期">
        <option value="daily">每日</option>
        <option value="weekly">每周</option>
      </select>
      <input v-model.number="targetCount" class="in target-in" type="number" min="1" max="20" aria-label="目标次数" />
      <span class="unit">次 / {{ period === 'daily' ? '天' : '周' }}</span>
      <button class="submit" type="submit" :disabled="!name.trim() || submitting">
        {{ submitting ? '创建中…' : '创建' }}
      </button>
    </form>

    <DomainState
      :loading="habits.loading && habits.items === null"
      loading-text="正在拉取习惯…"
      :error="habits.error"
      :empty="!habits.loading && habits.items !== null && habits.items.length === 0"
      empty-title="还没有在跟踪的习惯"
      @retry="habits.load()"
    >
      习惯是时间的复利。点右上「新建习惯」，或对左侧知时说<br />「帮我加一个每天喝水的习惯」——打卡与连续天数都会记在这里。
    </DomainState>

    <div v-if="habits.items && habits.items.length > 0" class="cards">
      <article v-for="h in habits.items" :key="h.id" class="habit-card" :data-done="h.status.done_today">
        <button
          class="check-btn"
          :aria-label="h.status.done_today ? `撤销 ${h.name} 今日打卡` : `为 ${h.name} 打卡`"
          :disabled="habits.pendingIds.includes(h.id)"
          @click="h.status.done_today ? habits.uncheckToday(h.id) : habits.checkInToday(h.id)"
        >
          <AppIcon :name="h.status.done_today ? 'check' : 'plus'" :size="17" />
          <span class="cb-text">{{ h.status.done_today ? '今日已打卡' : '打卡' }}</span>
        </button>

        <div class="hc-main">
          <div class="hc-title-row">
            <span class="dot" :style="h.color ? { background: h.color } : undefined" />
            <span class="hc-name">{{ h.name }}</span>
            <span class="hc-period">{{ PERIOD_LABEL[h.period] ?? h.period }} · 目标 {{ h.target_count }} 次</span>
          </div>
          <div class="hc-stats">
            <span class="hc-streak">连续 <b>{{ h.status.streak }}</b> 天</span>
            <span class="hc-count">今日 {{ h.status.today_count }}/{{ h.target_count }}</span>
          </div>
          <!-- 近 14 天打卡带 -->
          <div class="strip" :aria-label="`${h.name} 近 14 天打卡记录`">
            <span
              v-for="d in stripDays"
              :key="d"
              class="strip-dot"
              :data-c="dotClass(h.id, d)"
              :title="`${d}：${habits.logsByHabit[h.id]?.[d] ?? 0} 次`"
            />
          </div>
        </div>

        <button class="del" :aria-label="`删除习惯 ${h.name}`" title="删除习惯" @click="habits.remove(h.id)">
          <AppIcon name="x" :size="13" />
        </button>
      </article>
    </div>
  </section>
</template>

<style scoped>
.habits-view {
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

.hv-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.hv-caption {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.hv-date {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
}
.hv-note {
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

.creator {
  display: flex;
  align-items: center;
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
.name-in {
  flex: 1;
  min-width: 160px;
}
.target-in {
  width: 64px;
}
.unit {
  font-size: 12px;
  color: var(--ink-3);
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
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
  gap: 14px;
}
.habit-card {
  display: flex;
  gap: 14px;
  align-items: center;
  border: 1px solid var(--line-2);
  background: var(--bg-raise);
  border-radius: var(--radius-m);
  padding: 14px;
}
.habit-card[data-done='true'] {
  border-color: var(--line-hover);
}

.check-btn {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  width: 72px;
  height: 72px;
  border-radius: var(--radius-m);
  border: 1.5px solid var(--line-hover);
  color: var(--ink-2);
}
.check-btn:hover {
  border-color: var(--amber-dim);
  color: var(--amber-soft);
}
.check-btn:disabled {
  opacity: 0.55;
  cursor: default;
}
.habit-card[data-done='true'] .check-btn {
  background: var(--ok);
  border-color: var(--ok);
  color: var(--bg-app);
}
.cb-text {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
}

.hc-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.hc-title-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--amber);
  flex: none;
}
.hc-name {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--ink);
}
.hc-period {
  font-size: 11.5px;
  color: var(--ink-3);
}
.hc-stats {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: var(--ink-3);
}
.hc-streak b {
  font-family: var(--serif);
  font-size: 14px;
  color: var(--amber-soft);
}

/* 打卡带：14 格方块 */
.strip {
  display: flex;
  gap: 4px;
}
.strip-dot {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  background: var(--bg-sink);
  border: 1px solid var(--line);
}
.strip-dot[data-c='part'] {
  background: var(--amber-wash);
  border-color: var(--amber-border-weak);
}
.strip-dot[data-c='full'] {
  background: var(--amber-dim);
  border-color: var(--amber-dim);
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
