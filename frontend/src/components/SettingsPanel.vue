<script setup>
// 设置面板：开机自启（注册表）、知时助手悬浮窗、关闭按钮行为、AI 日报周报参数、数据互通。
// 功能模块开关（晨报/习惯/日记/目标/番茄钟）统一在「功能管理」面板，不在此处。
// 桌面环境经 IPC 读写；浏览器访问时桌面相关项禁用并提示仅在桌面应用内可用。
// 弹层基座为 BaseModal(Esc、焦点陷阱、z-index 统一),组件常驻、由 open 属性控制。
import { inject, onMounted, onBeforeUnmount, ref } from 'vue'
import ArtIcon from './ArtIcon.vue'
import BaseModal from './ui/BaseModal.vue'
import { getSettings, updateSettings } from '../api/settings'
import { exportTasksUrl, importTasksIcs } from '../api/ical'

defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

const api = window.electronAPI
const isDesktop = !!api?.isDesktop
const isPackaged = new URLSearchParams(location.search).get('packaged') === '1'
const isWin = api?.platform === 'win32'
// 仅安装版 Windows 支持真实开机自启；开发模式会污染注册表，浏览器/其他平台不可用
const autostartSupported = isDesktop && isPackaged && isWin
// 悬浮窗与关闭行为在桌面应用内有效（含开发模式 npm start）；浏览器访问时禁用
const desktopSupported = isDesktop

// 主题模式（由 App.vue provide）：auto 跟随系统 / light / dark
const { themeMode, setThemeMode } = inject('theme-mode', {
  themeMode: ref('auto'),
  setThemeMode: () => {},
})
const THEME_OPTIONS = [
  { value: 'auto', label: '跟随系统' },
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
]
const openAtLogin = ref(false)
const floatEnabled = ref(false)
const closeBehavior = ref('minimize') // minimize | quit | ask
// AI 日报周报个性化设置（后端应用设置，带默认值兜底）
const reportTaskLimit = ref(50)
const reportTimeout = ref(180)
const reportHistoryFilter = ref(true)
const loading = ref(true)
const saved = ref(false)
let savedTimer = null

const CLOSE_OPTIONS = [
  { value: 'minimize', label: '最小化到托盘' },
  { value: 'quit', label: '退出知时' },
  { value: 'ask', label: '每次询问' },
]

onMounted(async () => {
  // 并行读取：开机自启（注册表）+ 应用设置（后端）
  const jobs = []
  if (autostartSupported) {
    jobs.push(
      window.electronAPI
        .getLoginItemSettings()
        .then((v) => { openAtLogin.value = v })
        .catch(() => {})
    )
  }
  jobs.push(
    getSettings()
      .then((s) => {
        floatEnabled.value = s.assistant_float_enabled === 'true'
        closeBehavior.value = s.close_button_behavior || 'minimize'
        reportTaskLimit.value = Number(s.report_task_limit ?? 50) || 50
        reportTimeout.value = Number(s.report_timeout_seconds ?? 180) || 180
        reportHistoryFilter.value = s.report_history_filter !== 'false'
      })
      .catch(() => {})
  )
  await Promise.all(jobs)
  loading.value = false
})
onBeforeUnmount(() => clearTimeout(savedTimer))

async function toggleAutostart() {
  if (loading.value || !autostartSupported) return
  loading.value = true
  const next = !openAtLogin.value
  openAtLogin.value = next // 乐观更新
  try {
    // 主进程以注册表为准返回，可靠；采纳返回值以同步真实状态
    const real = await window.electronAPI.setLoginItemSettings(next)
    openAtLogin.value = real
    flashSaved()
  } catch {
    openAtLogin.value = !next // 写失败回滚
  } finally {
    loading.value = false
  }
}

async function toggleFloat() {
  if (loading.value || !desktopSupported) return
  const next = !floatEnabled.value
  floatEnabled.value = next
  const payload = { assistant_float_enabled: next ? 'true' : 'false' }
  try {
    await updateSettings(payload)
    // 通知主进程更新内存缓存并即时生效（preload 尚未提供时安全跳过）
    window.electronAPI?.notifySettingsChanged?.(payload)
    flashSaved()
  } catch {
    floatEnabled.value = !next
  }
}

async function selectCloseBehavior(value) {
  if (loading.value || !desktopSupported || value === closeBehavior.value) return
  const prev = closeBehavior.value
  closeBehavior.value = value
  const payload = { close_button_behavior: value }
  try {
    await updateSettings(payload)
    window.electronAPI?.notifySettingsChanged?.(payload)
    flashSaved()
  } catch {
    closeBehavior.value = prev
  }
}

// AI 报告设置：数值项失焦时提交并夹紧到合法区间，开关即时提交
async function saveReportNumber(key, refObj, min) {
  const v = Math.max(min, Number(refObj.value) || min)
  refObj.value = v
  try {
    await updateSettings({ [key]: String(v) })
    flashSaved()
  } catch {
    /* 保存失败静默，下次打开重新读取 */
  }
}
function changeReportTaskLimit() {
  return saveReportNumber('report_task_limit', reportTaskLimit, 1)
}
function changeReportTimeout() {
  return saveReportNumber('report_timeout_seconds', reportTimeout, 10)
}
async function toggleReportHistoryFilter() {
  const next = !reportHistoryFilter.value
  reportHistoryFilter.value = next
  try {
    await updateSettings({ report_history_filter: next ? 'true' : 'false' })
    flashSaved()
  } catch {
    reportHistoryFilter.value = !next
  }
}

function flashSaved() {
  saved.value = true
  clearTimeout(savedTimer)
  savedTimer = setTimeout(() => (saved.value = false), 1800)
}

const GITHUB_URL = 'https://github.com/Sirchen079/visual-schedule-planner'
function openGitHub() {
  // 桌面壳走系统默认浏览器；web 模式新标签打开
  if (window.electronAPI?.openExternal) window.electronAPI.openExternal(GITHUB_URL)
  else window.open(GITHUB_URL, '_blank', 'noopener')
}

// ---- 数据互通（iCal 导入导出）----
// toast 由 App.vue provide；提供降级以防组件树外调用
const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })
const icsInput = ref(null)
const importing = ref(false)

// 导出带 Content-Disposition attachment，直接跳转触发浏览器下载
function exportIcs() {
  window.location.href = exportTasksUrl()
}

function pickIcs() {
  icsInput.value?.click()
}

async function onIcsPicked(event) {
  const file = event.target.files?.[0]
  event.target.value = '' // 重置以便重复选择同一文件
  if (!file) return
  importing.value = true
  try {
    const res = await importTasksIcs(file)
    toast.success(`成功导入 ${res.created} 项任务`)
    // 通知主界面静默刷新任务列表（App.vue 监听该事件）
    window.dispatchEvent(new Event('tasks:refresh'))
  } catch (e) {
    toast.error(`导入失败：${e.message}`)
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <BaseModal :open="open" size="sm" :closable="false" label="设置" @close="emit('close')">
    <div class="panel">
      <div class="head">
        <div class="head-title">
          <ArtIcon name="assistant" tone="aqua" :size="28" tile label="设置" />
          <span>设置</span>
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

      <section class="row col-row">
        <div class="group-title">外观</div>
        <div class="sub-row">
          <div class="row-main">
            <div class="row-title">主题</div>
            <div class="row-desc">跟随系统时随 Windows 深浅色自动切换（含隔夜变化）；手动选择后将固定为主题</div>
          </div>
          <div class="segmented" role="radiogroup" aria-label="主题">
            <button
              v-for="opt in THEME_OPTIONS"
              :key="opt.value"
              class="seg-btn"
              role="radio"
              :aria-checked="themeMode === opt.value ? 'true' : 'false'"
              :class="{ active: themeMode === opt.value }"
              @click="setThemeMode(opt.value)"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
      </section>

      <section class="row" :class="{ disabled: !autostartSupported }">
        <div class="row-main">
          <div class="row-title">开机自启动</div>
          <div class="row-desc">
            <template v-if="!isDesktop">仅在桌面应用内可用（当前为浏览器访问）</template>
            <template v-else-if="!isPackaged">开发模式下不可用，请在安装版中开启</template>
            <template v-else-if="!isWin">仅 Windows 支持开机自启</template>
            <template v-else>开机时自动启动知时并弹出今日提醒</template>
          </div>
        </div>
        <button
          class="switch"
          role="switch"
          :aria-checked="openAtLogin ? 'true' : 'false'"
          :disabled="!autostartSupported || loading"
          :class="{ on: openAtLogin }"
          @click="toggleAutostart"
        >
          <span class="knob"></span>
        </button>
      </section>

      <section class="row" :class="{ disabled: !desktopSupported }">
        <div class="row-main">
          <div class="row-title">知时助手悬浮窗</div>
          <div class="row-desc">
            <template v-if="!isDesktop">仅在桌面应用内可用（当前为浏览器访问）</template>
            <template v-else>主窗口最小化到托盘后，在桌面显示悬浮按钮，点击即可向助手交代任务</template>
          </div>
        </div>
        <button
          class="switch"
          role="switch"
          :aria-checked="floatEnabled ? 'true' : 'false'"
          :disabled="!desktopSupported || loading"
          :class="{ on: floatEnabled }"
          @click="toggleFloat"
        >
          <span class="knob"></span>
        </button>
      </section>

      <section class="row col-row" :class="{ disabled: !desktopSupported }">
        <div class="row-main">
          <div class="row-title">关闭按钮行为</div>
          <div class="row-desc">
            <template v-if="!isDesktop">仅在桌面应用内可用（当前为浏览器访问）</template>
            <template v-else>点击主窗口关闭按钮时的行为</template>
          </div>
        </div>
        <div class="segmented" role="radiogroup" aria-label="关闭按钮行为">
          <button
            v-for="opt in CLOSE_OPTIONS"
            :key="opt.value"
            class="seg-btn"
            role="radio"
            :aria-checked="closeBehavior === opt.value ? 'true' : 'false'"
            :disabled="!desktopSupported || loading"
            :class="{ active: closeBehavior === opt.value }"
            @click="selectCloseBehavior(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </section>

      <section class="row col-row report-group">
        <div class="group-title">AI 日报周报</div>
        <div class="sub-row">
          <div class="row-main">
            <div class="row-title">每类任务上限</div>
            <div class="row-desc">报告里每一类（已完成/进行中/逾期等）最多展示的任务条数，超出部分会折叠，避免内容过长</div>
          </div>
          <input
            class="num-input"
            type="number"
            min="1"
            v-model.number="reportTaskLimit"
            @change="changeReportTaskLimit"
          />
        </div>
        <div class="sub-row">
          <div class="row-main">
            <div class="row-title">生成超时（秒）</div>
            <div class="row-desc">调用模型生成报告的最长等待时间，超时会提示重试</div>
          </div>
          <input
            class="num-input"
            type="number"
            min="10"
            v-model.number="reportTimeout"
            @change="changeReportTimeout"
          />
        </div>
        <div class="sub-row">
          <div class="row-main">
            <div class="row-title">历史按类型过滤</div>
            <div class="row-desc">开启后，日报/周报的历史列表只显示当前选中类型的报告</div>
          </div>
          <button
            class="switch"
            role="switch"
            :aria-checked="reportHistoryFilter ? 'true' : 'false'"
            :class="{ on: reportHistoryFilter }"
            @click="toggleReportHistoryFilter"
          >
            <span class="knob"></span>
          </button>
        </div>
      </section>

      <section class="row col-row ics-group">
        <div class="group-title">数据互通</div>
        <div class="sub-row">
          <div class="row-main">
            <div class="row-title">导出 .ics</div>
            <div class="row-desc">导出包含全部任务的起止/截止日期，可导入系统日历或其他日历应用</div>
          </div>
          <button class="ghost ics-btn" @click="exportIcs">导出 .ics</button>
        </div>
        <div class="sub-row">
          <div class="row-main">
            <div class="row-title">导入 .ics</div>
            <div class="row-desc">按 VEVENT 从日历文件创建新任务（上限 50MB）</div>
          </div>
          <button class="ghost ics-btn" :disabled="importing" @click="pickIcs">
            {{ importing ? '导入中…' : '导入 .ics' }}
          </button>
        </div>
        <input
          ref="icsInput"
          type="file"
          accept=".ics"
          class="ics-input"
          @change="onIcsPicked"
        />
      </section>

      <section
        class="row project-row"
        role="link"
        tabindex="0"
        @click="openGitHub"
        @keydown.enter.prevent="openGitHub"
      >
        <div class="row-main">
          <div class="row-title">项目主页</div>
          <div class="row-desc">如果喜欢知时，欢迎给个 ⭐ Star 支持一下</div>
        </div>
        <span class="link-tag">
          <ArtIcon name="link" tone="aqua" :size="18" label="GitHub 项目主页" />
          <span>GitHub</span>
        </span>
      </section>
    </div>
  </BaseModal>
</template>

<style scoped>
.panel {
  padding: 22px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
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

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 14px;
  border-radius: var(--radius);
  background: var(--surface-2);
  border: 1px solid transparent;
  margin-bottom: 12px;
}
.row:last-child {
  margin-bottom: 0;
}
.row.disabled {
  opacity: 0.66;
}
.row.col-row {
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
}
.report-group {
  gap: 10px;
}
.group-title {
  font-size: 13px;
  font-weight: 800;
  color: var(--accent-strong);
  letter-spacing: 0.5px;
}
.sub-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.num-input {
  width: 72px;
  padding: 7px 8px;
  text-align: center;
  font-size: 14px;
  font-weight: 650;
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text);
  box-shadow: var(--shadow-inset);
}
.num-input:focus {
  outline: none;
  border-color: var(--accent);
}
.row-main {
  min-width: 0;
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

.segmented {
  display: flex;
  gap: 6px;
}
.seg-btn {
  flex: 1;
  min-width: 0;
  padding: 9px 6px;
  font-size: 12px;
  font-weight: 650;
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text-soft);
  box-shadow: var(--shadow-inset);
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.seg-btn:hover:not(:disabled):not(.active) {
  color: var(--text);
  background: var(--surface-2);
}
.seg-btn.active {
  color: #fff;
  background: var(--btn-gradient);
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
  box-shadow: 0 4px 14px var(--accent-glow);
}
.seg-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

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

.ics-group {
  gap: 10px;
}
.ics-btn {
  flex-shrink: 0;
  min-width: 96px;
  padding: 8px 14px;
  font-size: 13px;
  border-radius: var(--radius-sm);
}
.ics-input {
  display: none;
}

.project-row {
  cursor: pointer;
}
.project-row:hover {
  border-color: var(--border);
  background: var(--surface);
}
.project-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.link-tag {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--accent-hover);
  background: var(--accent-soft);
  padding: 7px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
}
</style>
