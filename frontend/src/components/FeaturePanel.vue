<script setup>
// 功能管理面板：按需开关功能模块（习惯/日记/目标/番茄钟/每日晨报/秘书自动档/内嵌 AI 动作/伴随联动）。
// 关闭只隐藏入口（导航/快捷键/AI 工具），数据完整保留；值为后端应用设置 "true"/"false"。
// 接线约定（供 App.vue 使用）：
//   props: open (Boolean) —— 组件常驻挂载，由 open 控制显隐
//   emits:
//     close            —— 请求关闭面板
//     changed(settings) —— 任一开关保存成功后触发，settings 为本面板管理的 8 个键的
//                          'true'/'false' 快照（形如 { feature_habits_enabled: 'true', ... }），
//                          App 可据此即时隐藏 tab/快捷键等入口
// 开关样式与「已保存」闪烁提示复用 SettingsPanel 的结构。
import { inject, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import ArtIcon from './ArtIcon.vue'
import BaseModal from './ui/BaseModal.vue'
import { getSettings, updateSettings } from '../api/settings'

const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'changed'])

const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })

// 缺省值：前四个模块默认开启，晨报/自动档/伴随联动默认关闭，内嵌 AI 动作默认开启
// （与后端/设置面板口径一致）
const DEFAULTS = {
  feature_habits_enabled: 'true',
  feature_journal_enabled: 'true',
  feature_goals_enabled: 'true',
  feature_timer_enabled: 'true',
  proactive_briefing_enabled: 'false',
  feature_autopilot_enabled: 'false',
  feature_inline_ai_enabled: 'true',
  feature_companion_enabled: 'false',
}

const MODULES = [
  {
    key: 'feature_habits_enabled',
    icon: 'steps',
    name: '习惯打卡',
    desc: '每日/每周打卡与连续纪录',
  },
  {
    key: 'feature_journal_enabled',
    icon: 'file',
    name: '日记',
    desc: '一天一篇 Markdown 日记',
  },
  {
    key: 'feature_goals_enabled',
    icon: 'flag',
    name: '目标 OKR',
    desc: '长期目标与关键结果跟踪',
  },
  {
    key: 'feature_timer_enabled',
    icon: 'restore',
    name: '番茄钟',
    desc: '专注计时与时间投入统计',
  },
  {
    key: 'proactive_briefing_enabled',
    icon: 'sun',
    name: '每日晨报',
    desc: '每天首次启动生成今日简报（消耗一次模型调用）',
  },
  {
    key: 'feature_autopilot_enabled',
    icon: 'assistant',
    name: '秘书自动档',
    desc: '每天启动时主动为你排程与拆解任务（消耗少量模型调用）',
    agentOnly: true,
  },
  {
    key: 'feature_inline_ai_enabled',
    icon: 'send',
    name: '内嵌 AI 动作',
    desc: '任务与日记里的一键 AI 直接执行',
  },
  {
    key: 'feature_companion_enabled',
    icon: 'check',
    name: '伴随联动',
    desc: '番茄钟收束语等场景化微行动（按次消耗模型调用）',
    agentOnly: true,
  },
]

const values = reactive({})
const isAgentMode = ref(true) // 知时代理模式；原版知时助手下代理专属能力禁用
const loading = ref(true)
const saved = ref(false)
let savedTimer = null

async function loadSettings() {
  try {
    const s = await getSettings()
    for (const m of MODULES) values[m.key] = (s[m.key] ?? DEFAULTS[m.key]) === 'true'
    isAgentMode.value = (s.assistant_mode ?? 'agent') !== 'assistant'
  } catch {
    // 读取失败按缺省值展示，用户仍可切换（写失败会回滚）
    for (const m of MODULES) values[m.key] = DEFAULTS[m.key] === 'true'
  } finally {
    loading.value = false
  }
}
onMounted(loadSettings)
// 助手模式可能在 AssistantView 里随时切换，组件又是常驻挂载、onMounted 只读一次；
// 每次打开面板时重读最新设置，让「秘书自动档」「伴随联动」等代理专属开关的可选性随模式同步
watch(() => props.open, (open) => {
  if (open) loadSettings()
})
onBeforeUnmount(() => clearTimeout(savedTimer))

function flashSaved() {
  saved.value = true
  clearTimeout(savedTimer)
  savedTimer = setTimeout(() => (saved.value = false), 1800)
}

function snapshot() {
  const out = {}
  for (const m of MODULES) out[m.key] = values[m.key] ? 'true' : 'false'
  return out
}

// 乐观更新：失败回滚并提示
async function toggle(mod) {
  if (loading.value) return
  if (mod.agentOnly && !isAgentMode.value) return // 代理专属：原版助手模式下不可开
  const next = !values[mod.key]
  values[mod.key] = next
  try {
    await updateSettings({ [mod.key]: next ? 'true' : 'false' })
    flashSaved()
    emit('changed', snapshot())
  } catch (e) {
    values[mod.key] = !next
    toast.error(`保存失败：${e.message}`)
  }
}
</script>

<template>
  <BaseModal :open="open" size="sm" :closable="false" label="功能管理" @close="emit('close')">
    <div class="panel">
      <div class="head">
        <div class="head-title">
          <ArtIcon name="board" tone="aqua" :size="28" tile label="功能管理" />
          <span>功能管理</span>
        </div>
        <div class="head-right">
          <Transition name="fade">
            <span v-if="saved" class="saved-hint">已保存</span>
          </Transition>
          <button class="ghost close-btn" @click="emit('close')">
            <ArtIcon name="close" tone="pearl" :size="18" />
            <span>关闭</span>
          </button>
        </div>
      </div>

      <p class="panel-desc muted">
        按需开关功能模块；关闭只隐藏入口（导航/快捷键/AI 工具），数据完整保留，随时可重新开启。
      </p>

      <section v-for="mod in MODULES" :key="mod.key" class="row" :class="{ 'row-disabled': mod.agentOnly && !isAgentMode }">
        <div class="row-icon">
          <ArtIcon :name="mod.icon" tone="aqua" :size="30" tile :label="mod.name" />
        </div>
        <div class="row-main">
          <div class="row-title">
            {{ mod.name }}
            <span v-if="mod.agentOnly" class="agent-badge">知时代理专属</span>
          </div>
          <div class="row-desc">
            {{ mod.agentOnly && !isAgentMode ? '当前为「知时助手」模式，在助手中切换到知时代理后可用' : mod.desc }}
          </div>
        </div>
        <button
          class="switch"
          role="switch"
          :aria-checked="values[mod.key] ? 'true' : 'false'"
          :aria-label="`${mod.name}开关`"
          :disabled="loading || (mod.agentOnly && !isAgentMode)"
          :class="{ on: values[mod.key] }"
          @click="toggle(mod)"
        >
          <span class="knob"></span>
        </button>
      </section>
    </div>
  </BaseModal>
</template>

<style scoped>
.row-disabled {
  opacity: 0.55;
}

.agent-badge {
  margin-left: 6px;
  padding: 1px 6px;
  font-size: 11px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent);
  vertical-align: 1px;
}

.panel {
  padding: 22px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.head-title {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-size: 18px;
  font-weight: 800;
  color: var(--text);
}
.head-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.close-btn {
  min-height: 34px;
  padding: 7px 12px;
  display: flex;
  align-items: center;
  gap: 5px;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.panel-desc {
  margin: 0 0 14px;
  line-height: 1.6;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border-radius: var(--radius);
  background: var(--surface-2);
  border: 1px solid transparent;
  margin-bottom: 12px;
}
.row:last-child {
  margin-bottom: 0;
}
.row-icon {
  flex-shrink: 0;
}
.row-main {
  min-width: 0;
  flex: 1;
}
.row-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}
.row-desc {
  margin-top: 3px;
  font-size: 12px;
  color: var(--text-soft);
}
.saved-hint {
  font-size: 12px;
  font-weight: 700;
  color: var(--success);
  white-space: nowrap;
}

/* 开关结构与 SettingsPanel 一致 */
.switch {
  flex-shrink: 0;
  width: 46px;
  height: 26px;
  min-width: 46px;
  padding: 3px;
  border-radius: var(--radius-pill);
  background: var(--surface-3);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
  display: inline-flex;
  align-items: center;
  transition: background 0.18s ease, border-color 0.18s ease;
}
.switch:hover {
  background: var(--surface-3);
}
.switch.on {
  background: var(--btn-gradient);
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
}
.switch.on:hover {
  background: var(--btn-gradient-hover);
}
.switch .knob {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  box-shadow: var(--shadow-sm);
  transition: transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.switch.on .knob {
  transform: translateX(20px);
}
.switch:disabled {
  cursor: default;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
