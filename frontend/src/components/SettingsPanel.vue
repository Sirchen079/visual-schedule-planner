<script setup>
// 设置面板：当前仅含「开机自启」开关。桌面环境经 IPC 读写注册表；
// 浏览器访问时开关禁用并提示仅在桌面应用内可用。
import { onMounted, onBeforeUnmount, ref } from 'vue'
import ArtIcon from './ArtIcon.vue'

const emit = defineEmits(['close'])

const api = window.electronAPI
const isDesktop = !!api?.isDesktop
// isPackaged 由主进程经 URL ?packaged=1 传入（sandbox 下 preload 无法读取 app.isPackaged）
const isPackaged = new URLSearchParams(location.search).get('packaged') === '1'
const isWin = api?.platform === 'win32'
// 仅安装版 Windows 支持真实开机自启；开发模式会污染注册表，浏览器/其他平台不可用
const supported = isDesktop && isPackaged && isWin
const openAtLogin = ref(false)
const loading = ref(true)
const saved = ref(false)
let savedTimer = null

onMounted(async () => {
  if (!supported) {
    loading.value = false
    return
  }
  try {
    openAtLogin.value = await window.electronAPI.getLoginItemSettings()
  } catch {
    // 读取失败按关闭处理，不阻断面板使用
  }
  loading.value = false
})
onBeforeUnmount(() => clearTimeout(savedTimer))

async function toggle() {
  if (loading.value || !supported) return
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

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="panel">
      <div class="head">
        <div class="head-title">
          <ArtIcon name="assistant" tone="aqua" :size="28" tile label="设置" />
          <span>设置</span>
        </div>
        <button class="ghost close-btn" @click="emit('close')">
          <ArtIcon name="close" tone="pearl" :size="18" />
          <span>关闭</span>
        </button>
      </div>

      <section class="row" :class="{ disabled: !supported }">
        <div class="row-main">
          <div class="row-title">开机自启动</div>
          <div class="row-desc">
            <template v-if="!isDesktop">仅在桌面应用内可用（当前为浏览器访问）</template>
            <template v-else-if="!isPackaged">开发模式下不可用，请在安装版中开启</template>
            <template v-else-if="!isWin">仅 Windows 支持开机自启</template>
            <template v-else>开机时自动启动知时并弹出今日提醒</template>
          </div>
          <Transition name="fade">
            <span v-if="saved" class="saved-hint">已保存</span>
          </Transition>
        </div>
        <button
          class="switch"
          role="switch"
          :aria-checked="openAtLogin ? 'true' : 'false'"
          :disabled="!supported || loading"
          :class="{ on: openAtLogin }"
          @click="toggle"
        >
          <span class="knob"></span>
        </button>
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
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 130;
  background: rgba(23, 74, 102, 0.28);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  animation: overlay-in 0.25s ease;
}
@keyframes overlay-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.panel {
  width: 420px;
  max-width: 92vw;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  padding: 22px;
  animation: panel-in 0.22s ease-out;
}
@keyframes panel-in {
  from { opacity: 0; transform: translateY(12px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
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
}
.row.disabled {
  opacity: 0.66;
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
  font-size: 12.5px;
  color: var(--text-soft);
}
.saved-hint {
  display: inline-block;
  margin-top: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--success);
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
  background: linear-gradient(135deg, var(--accent), #62b8d2);
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
}
.switch.on:hover {
  background: linear-gradient(135deg, var(--accent-hover), var(--accent));
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
