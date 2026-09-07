<script setup lang="ts">
import { computed } from 'vue'
import { useUpdatesStore } from '../../stores/updates'
const props = defineProps<{ inline?: boolean; lockOnly?: boolean }>()
const updates = useUpdatesStore()
const state = computed(() => updates.state)
const busy = computed(() => !!state.value && ['checking', 'downloading', 'preparing', 'installing'].includes(state.value.status))
const label = computed(() => {
  switch (state.value?.status) {
    case 'checking': return '正在检查 GitHub 新版本…'
    case 'available': return `知时 ${state.value.version} 可以更新`
    case 'downloading': return `正在下载 ${state.value.version} · ${Math.round(state.value.percent)}%`
    case 'downloaded': return `${state.value.version} 已下载，可以安装`
    case 'preparing': return '正在保存窗口与草稿…'
    case 'installing': return '正在关闭知时并启动安装…'
    case 'unavailable': return '开发预览中不启用自动更新'
    case 'error': return '更新暂未完成'
    default: return state.value?.checkedAt ? '当前已是最新发布版本' : '启动后自动检查新版本'
  }
})
</script>

<template>
  <section v-if="state && !props.lockOnly && (props.inline || updates.showBanner)" class="app-update" :class="{ 'update-inline': props.inline }" aria-label="知时更新">
    <div class="update-title"><strong>{{ label }}</strong><button v-if="!props.inline && !busy" class="dismiss" aria-label="稍后更新" @click="updates.dismissedVersion = state.version">×</button></div>
    <p v-if="props.inline">当前版本 {{ state.currentVersion }} · 来源：GitHub 官方发布页</p>
    <p v-if="state.status === 'available'">安装会重启知时，数据与设置将保留。</p>
    <progress v-if="state.status === 'downloading'" :value="state.percent" max="100" aria-label="更新下载进度" />
    <p v-if="state.error || updates.actionError" role="alert" class="update-error">{{ state.error || updates.actionError }}</p>
    <div class="update-actions">
      <button v-if="state.status === 'downloaded'" class="primary" @click="updates.act('install')">安装并重启</button>
      <button v-else-if="state.version && ['available','error'].includes(state.status)" class="primary" :disabled="busy" @click="updates.act('downloadAndInstall')">{{ state.status === 'error' ? '重试下载安装' : '下载并安装' }}</button>
      <button v-if="props.inline" :disabled="busy || state.status === 'unavailable' || state.status === 'downloaded'" @click="updates.act('check')">检查更新</button>
      <button v-if="props.inline || state.error" :disabled="updates.locking" @click="updates.act('openReleases')">发布说明</button>
    </div>
  </section>
  <div v-if="!props.inline && updates.locking" class="update-lock" role="alert" aria-live="assertive"><strong>{{ label }}</strong><p>保存完成后将打开安装程序。</p></div>
</template>

<style scoped>
.app-update { position:fixed; bottom:16px; left:96px; width:min(360px,calc(100vw - 112px)); z-index:95; padding:16px; border:1px solid var(--line-2); border-radius:12px; background:var(--bg-raise); box-shadow:0 4px 24px #0002; color:var(--ink); }
.update-inline { position:static; grid-column:1 / -1; width:auto; margin-top:20px; box-shadow:none; background:var(--bg-app); }
.update-title { display:flex; align-items:center; justify-content:space-between; gap:12px; font-size:13px; }
.dismiss { font-size:20px; padding:0 4px; }
p { margin:8px 0; font-size:12px; color:var(--ink-2); line-height:1.6; }
.update-actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
.update-actions button { border:1px solid var(--line-2); border-radius:7px; padding:7px 10px; font-size:12px; }
.update-actions .primary { background:var(--amber); color:var(--bg-app); border-color:var(--amber); }
button:disabled { opacity:.5; cursor:wait; }
button:focus-visible { outline:2px solid var(--amber); outline-offset:3px; }
progress { width:100%; height:6px; accent-color:var(--amber); margin-top:12px; }
.update-error { color:var(--terra-soft); }
.update-lock { position:fixed; inset:0; z-index:10000; background:var(--bg-app); display:flex; flex-direction:column; justify-content:center; align-items:center; padding:24px; text-align:center; }
</style>
