<script setup lang="ts">
/**
 * 番茄钟浮动条（壳层右下 fixed，全页面可见，不遮挡主内容）。
 * 两态：
 * - 空闲：小条「专注 · 今日已专注 X 分钟」+「记录」入口；点小条展开开始表单（任务标题可空、
 *   专注/休息切换、开始），点「记录」展开今日记录面板（起止/分钟/两段确认删除）
 * - 进行中：kind 徽章（专注/休息）+ task_title + mm:ss 本地秒针 + 「结束」
 * 计时数据全部来自 focus store（current + started_at 本地推算 + 45s 对账防漂移）。
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import AppIcon from '../AppIcon.vue'
import { registerEscLayer, registerFocusFormControl } from '../../composables/hotkeyPorts'
import { useFocusStore } from '../../stores/focus'
import type { FocusKind, FocusLog } from '../../api/focus'

const focus = useFocusStore()

const KIND_LABEL: Record<FocusKind, string> = { focus: '专注', break: '休息' }

/** 进行中徽标文案：契约 TimeLogOut.kind 为自由串，按实际取值映射（未知回落「专注」）。 */
const runningKindLabel = computed(() =>
  focus.current?.kind === 'break' ? KIND_LABEL.break : KIND_LABEL.focus,
)

/** 记录行的 kind 标签：未知值回落「专注」。 */
function kindLabelOf(kind: string): string {
  return kind === 'break' ? KIND_LABEL.break : KIND_LABEL.focus
}

/** 本地 naive ISO → HH:mm（解析失败回落占位）。 */
function hmOf(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '--:--'
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 起止 HH:mm–HH:mm；进行中（ended_at 为空）只给起点。 */
function timeRange(log: FocusLog): string {
  return log.ended_at ? `${hmOf(log.started_at)}–${hmOf(log.ended_at)}` : `${hmOf(log.started_at)}–`
}

const expanding = ref(false)
const title = ref('')
const kind = ref<FocusKind>('focus')

const logsOpen = ref(false)
/** 两段确认删除：当前处于「确认删除？」态的记录 id */
const confirmingId = ref<number | null>(null)

const todayLabel = computed(() => `今日已专注 ${focus.todayMinutes} 分钟`)
const currentTitle = computed(() => {
  const t = focus.current?.task_title?.trim()
  return t ? t : '未命名专注'
})

function toggleExpand(): void {
  expanding.value = !expanding.value
  title.value = ''
  kind.value = 'focus'
  // 开始表单与记录面板互斥：展开表单时收起记录面板
  if (expanding.value && logsOpen.value) {
    logsOpen.value = false
    confirmingId.value = null
  }
}

function toggleLogs(): void {
  logsOpen.value = !logsOpen.value
  confirmingId.value = null
}

async function begin(): Promise<void> {
  await focus.start(kind.value, title.value.trim())
  if (!focus.error) expanding.value = false
}

async function finish(): Promise<void> {
  await focus.stop()
}

async function confirmRemove(id: number): Promise<void> {
  confirmingId.value = null
  await focus.removeLog(id)
}

/* ---- 快捷键端口----
 * f 键空闲时展开本表单（等价于点空闲小条）、Esc 第②层收起：向 hotkeyPorts 登记控制入口；
 * 表单展开期间注册 tier 2 的 Esc 分层条目，关闭/卸载即注销（不泄漏）。
 * 「记录」面板同层：面板开着才注册、关掉即注销。FocusBar 与壳层同生命周期，
 * 控制入口在全局键激活期间始终可用。 */
const deregFocusControl = registerFocusFormControl({
  expand: () => {
    if (!expanding.value && !focus.isRunning) toggleExpand()
  },
  collapse: () => {
    if (expanding.value) toggleExpand()
  },
})
let deregEscLayer: (() => void) | null = null
watch(expanding, (open) => {
  if (open) deregEscLayer = registerEscLayer({ tier: 2, close: () => toggleExpand() })
  else {
    deregEscLayer?.()
    deregEscLayer = null
  }
})
let deregLogsEscLayer: (() => void) | null = null
watch(logsOpen, (open) => {
  if (open) {
    void focus.loadLogs()
    deregLogsEscLayer = registerEscLayer({ tier: 2, close: () => toggleLogs() })
  } else {
    deregLogsEscLayer?.()
    deregLogsEscLayer = null
  }
})
onUnmounted(() => {
  deregFocusControl()
  deregEscLayer?.()
  deregEscLayer = null
  deregLogsEscLayer?.()
  deregLogsEscLayer = null
})
</script>

<template>
  <div class="focusbar" :data-running="focus.isRunning">
    <!-- 进行中 -->
    <template v-if="focus.isRunning">
      <span class="kind" :data-kind="focus.current?.kind">{{ runningKindLabel }}</span>
      <span class="t" :title="currentTitle">{{ currentTitle }}</span>
      <span class="mmss">{{ focus.elapsedLabel }}</span>
      <button class="stop" :disabled="focus.stopping" @click="finish">
        {{ focus.stopping ? '结束中…' : '结束' }}
      </button>
    </template>

    <!-- 空闲：今日记录面板（浮动条上方、右下对齐） + 小条 + 记录入口 -->
    <template v-else-if="!expanding">
      <div v-if="logsOpen" id="focus-logs-panel" class="logs-panel" role="region" aria-label="今日专注记录">
        <div class="lp-head">
          <span class="lp-cap">今日记录</span>
          <button class="lp-close" title="收起" aria-label="收起今日记录" @click="toggleLogs">
            <AppIcon name="x" :size="13" />
          </button>
        </div>
        <p v-if="focus.logsError" class="lp-err" role="alert">{{ focus.logsError }}</p>
        <p v-if="focus.logActionError" class="lp-err" role="alert">{{ focus.logActionError }}</p>
        <p v-if="focus.logsLoading" class="lp-note">加载中…</p>
        <p v-else-if="!focus.logs || focus.logs.length === 0" class="lp-note">今日还没有专注记录</p>
        <ul v-else class="lp-list">
          <li v-for="log in focus.logs" :key="log.id" class="lp-item">
            <span class="lp-kind" :data-kind="log.kind">{{ kindLabelOf(log.kind) }}</span>
            <span class="lp-title" :title="log.task_title?.trim() || '未关联任务'">
              {{ log.task_title?.trim() || '未关联任务' }}
            </span>
            <span class="lp-time">{{ timeRange(log) }}</span>
            <span class="lp-min">{{ log.minutes }}分</span>
            <span v-if="log.ended_at === null" class="lp-live">进行中</span>
            <template v-else>
              <button
                v-if="confirmingId !== log.id"
                class="lp-del danger"
                @click="confirmingId = log.id"
              >
                删除
              </button>
              <template v-else>
                <button class="lp-del danger" @click="confirmRemove(log.id)">确认删除？</button>
                <button class="lp-del" @click="confirmingId = null">取消</button>
              </template>
            </template>
          </li>
        </ul>
      </div>

      <div class="idle-row">
        <button class="idle" @click="toggleExpand">
          <AppIcon name="timer" :size="14" />
          <span class="idle-cap">专注</span>
          <span class="idle-dot">·</span>
          <span class="idle-today">{{ todayLabel }}</span>
        </button>
        <button
          class="rec-btn"
          :aria-expanded="logsOpen"
          aria-controls="focus-logs-panel"
          @click="toggleLogs"
        >
          记录
        </button>
      </div>
    </template>

    <!-- 空闲：开始表单 -->
    <div v-else class="form">
      <input
        v-model="title"
        class="ti"
        placeholder="在做什么？（可留空）"
        maxlength="120"
        @keydown.enter="begin"
      />
      <div class="f-row">
        <div class="seg" role="tablist" aria-label="计时类型">
          <button
            v-for="k in (['focus', 'break'] as const)"
            :key="k"
            class="seg-btn"
            :class="{ on: kind === k }"
            role="tab"
            :aria-selected="kind === k"
            @click="kind = k"
          >
            {{ KIND_LABEL[k] }}
          </button>
        </div>
        <button class="go" :disabled="focus.starting" @click="begin">
          {{ focus.starting ? '启动中…' : '开始' }}
        </button>
        <button class="cancel" title="收起" aria-label="收起开始表单" @click="toggleExpand">
          <AppIcon name="x" :size="13" />
        </button>
      </div>
    </div>

    <p v-if="focus.error" class="err" role="alert">{{ focus.error }}</p>
  </div>
</template>

<style scoped>
.focusbar {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 25;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: stretch;
  max-width: min(420px, calc(100vw - 32px));
}

/* 空闲小条 */
.idle-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
.idle {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--ink-2);
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 7px 14px;
  box-shadow: var(--shadow-panel);
}
.idle:hover {
  border-color: var(--line-hover);
  color: var(--ink);
}
.idle-cap {
  font-weight: 600;
  letter-spacing: 0.04em;
}
.idle-dot,
.idle-today {
  color: var(--ink-3);
  white-space: nowrap;
}
/* 「记录」入口：ghost 按钮惯例（act 同族），pill 形与 idle 小条对齐 */
.rec-btn {
  flex: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--amber-soft);
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 7px 12px;
  box-shadow: var(--shadow-panel);
}
.rec-btn:hover {
  border-color: var(--line-hover);
}
.rec-btn[aria-expanded='true'] {
  border-color: var(--amber-border-dim);
}

/* 今日记录面板：浮动条上方、右下对齐，超高滚动 */
.logs-panel {
  align-self: flex-end;
  width: min(360px, calc(100vw - 32px));
  max-height: min(320px, 45vh);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 7px;
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-m);
  padding: 10px 12px;
  box-shadow: var(--shadow-panel);
}
.lp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.lp-cap {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-3);
}
.lp-close {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  color: var(--ink-3);
}
.lp-close:hover {
  border-color: var(--line-hover);
  color: var(--ink-2);
}
.lp-note {
  font-size: 12px;
  color: var(--ink-3);
  padding: 2px 0 4px;
}
.lp-err {
  font-size: 11.5px;
  color: var(--terra-soft);
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 5px 9px;
}
.lp-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.lp-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.lp-kind {
  flex: none;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border-dim);
  background: var(--amber-wash);
  border-radius: var(--radius-pill);
  padding: 1px 7px;
}
.lp-kind[data-kind='break'] {
  color: var(--ok);
  border-color: var(--line-2);
  background: none;
}
.lp-title {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lp-time {
  flex: none;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}
.lp-min {
  flex: none;
  min-width: 34px;
  text-align: right;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
.lp-live {
  flex: none;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border-dim);
  background: var(--amber-wash);
  border-radius: var(--radius-pill);
  padding: 1px 7px;
}
.lp-del {
  flex: none;
  font-size: 11px;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 2px 8px;
}
.lp-del.danger {
  color: var(--terra-soft);
}
.lp-del:hover {
  border-color: var(--line-hover);
  color: var(--ink-2);
}
.lp-del.danger:hover {
  color: var(--terra-soft);
  border-color: var(--terra-dashed);
}

/* 进行中 */
.focusbar[data-running='true'] {
  flex-direction: row;
  align-items: center;
  gap: 10px;
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-l);
  padding: 8px 10px 8px 14px;
  box-shadow: var(--shadow-panel);
}
.kind {
  flex: none;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border-dim);
  background: var(--amber-wash);
  border-radius: var(--radius-pill);
  padding: 2px 9px;
}
.kind[data-kind='break'] {
  color: var(--ok);
  border-color: var(--line-2);
  background: none;
}
.t {
  font-size: 12.5px;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.mmss {
  flex: none;
  margin-left: auto;
  font-family: var(--mono);
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: 0.04em;
  font-variant-numeric: tabular-nums;
}
.stop {
  flex: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--btn-new-text);
  background: var(--btn-new-bg);
  border-radius: var(--radius-s);
  padding: 5px 12px;
}
.stop:hover:not(:disabled) {
  background: var(--btn-new-bg-hover);
}
.stop:disabled {
  /* 实底填充白字禁用件：浅色 solid 档 0.9 才 ≥3:1；暗色 fallback 0.5 不变 */
  opacity: var(--ctl-disabled-opacity-solid, 0.5);
  cursor: default;
}

/* 开始表单 */
.form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-m);
  padding: 10px 12px;
  box-shadow: var(--shadow-panel);
}
.ti {
  width: 100%;
  font-family: inherit;
  font-size: 12.5px;
  color: var(--ink);
  background: var(--bg-app);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 7px 10px;
}
.ti::placeholder {
  color: var(--ink-faint);
}
.ti:focus {
  outline: none;
  border-color: var(--line-hover);
}
.f-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.seg {
  display: flex;
  border: 1px solid var(--line-2);
  border-radius: 8px;
  overflow: hidden;
}
.seg-btn {
  padding: 4px 11px;
  font-size: 12px;
  color: var(--ink-3);
}
.seg-btn + .seg-btn {
  border-left: 1px solid var(--line);
}
.seg-btn:hover {
  color: var(--ink-2);
}
.seg-btn.on {
  background: var(--amber-wash);
  color: var(--amber-soft);
}
.go {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
  color: var(--btn-new-text);
  background: var(--btn-new-bg);
  border-radius: var(--radius-s);
  padding: 5px 13px;
}
.go:hover:not(:disabled) {
  background: var(--btn-new-bg-hover);
}
.go:disabled {
  /* 同 stop：浅色 solid 档 0.9、暗色 fallback 0.5 不变 */
  opacity: var(--ctl-disabled-opacity-solid, 0.5);
  cursor: default;
}
.cancel {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  color: var(--ink-3);
}
.cancel:hover {
  border-color: var(--line-hover);
  color: var(--ink-2);
}

.err {
  font-size: 11.5px;
  color: var(--terra-soft);
  background: var(--bg-raise);
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 6px 10px;
}

@media (max-width: 880px) {
  .focusbar {
    right: 10px;
    bottom: 10px;
    max-width: calc(100vw - 20px);
  }
  .form {
    width: min(320px, calc(100vw - 20px));
  }
  .logs-panel {
    width: min(320px, calc(100vw - 20px));
  }
}
</style>
