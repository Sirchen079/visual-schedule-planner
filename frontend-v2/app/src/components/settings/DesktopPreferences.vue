<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const desktop = window.zhishiDesktop
const state = ref<DesktopPreferences | null>(null)
const error = ref(''), busy = ref(false), loaded = ref(false)
let unsubscribe: (() => void) | undefined
async function load() {
  if (!desktop) return
  try { state.value = await desktop.preferences(); error.value = '' }
  catch (e) { error.value = e instanceof Error ? e.message : '桌面设置读取失败' }
  finally { loaded.value = true }
}
async function change(key: 'visible' | 'pinned' | 'collapsed' | 'notifications' | 'resetPosition', value: boolean) {
  if (!desktop || busy.value) return
  busy.value = true; error.value = ''
  try { state.value = await desktop.updatePreferences({ [key]: value }) }
  catch (e) { error.value = e instanceof Error ? e.message : '设置未保存，请重试' }
  finally { busy.value = false }
}
onMounted(() => { void load(); unsubscribe = desktop?.onPreferencesChanged(s => { state.value = s }); window.addEventListener('focus', load) })
onUnmounted(() => { unsubscribe?.(); window.removeEventListener('focus', load) })
</script>

<template>
  <section id="settings-desktop" class="desktop-panel" aria-labelledby="desktop-title">
    <header><h2 id="desktop-title">悬浮窗与桌面通知</h2><span>更改后自动保存</span></header>
    <p v-if="!desktop" class="hint">请在新版知时桌面应用中打开此页，设置悬浮窗与系统通知。浏览器中仍可调整下方的其他功能。</p>
    <p v-else-if="!loaded" class="hint">正在读取桌面设置…</p>
    <p v-if="error" class="error" role="alert">{{ error }} <button @click="load">重试</button></p>
    <template v-if="state">
      <div class="preference-row">
        <div><strong>显示悬浮窗</strong><p>在桌面随时与知时对话。关闭后，下次启动也保持关闭。</p></div>
        <button id="pref-widget-visible" class="switch" role="switch" aria-label="显示悬浮窗" :aria-checked="state.visible" :disabled="busy" @click="change('visible', !state.visible)"><span></span></button>
      </div>
      <div class="preference-row">
        <div><strong>始终置顶</strong><p>悬浮窗显示在其他应用上方。</p></div>
        <button id="pref-widget-pinned" class="switch" role="switch" aria-label="始终置顶" :aria-checked="state.pinned" :disabled="busy" @click="change('pinned', !state.pinned)"><span></span></button>
      </div>
      <div class="preference-row">
        <div><strong>收起为小条</strong><p>缩小占用空间，需要时再展开对话。</p></div>
        <button id="pref-widget-collapsed" class="switch" role="switch" aria-label="收起为小条" :aria-checked="state.collapsed" :disabled="busy" @click="change('collapsed', !state.collapsed)"><span></span></button>
      </div>
      <div class="preference-row">
        <div><strong>找回悬浮窗位置</strong><p>将悬浮窗移回主屏幕右上方。</p></div>
        <button id="pref-widget-reset" class="action" :disabled="busy" @click="change('resetPosition', true)">重置位置</button>
      </div>
      <div class="preference-row">
        <div><strong>桌面通知</strong><p>知时在后台时，用系统弹窗提醒。关闭后，仍可在右上角铃铛查看通知。</p></div>
        <button id="pref-notifications" class="switch" role="switch" aria-label="桌面通知" :aria-checked="state.notifications" :disabled="busy" @click="change('notifications', !state.notifications)"><span></span></button>
      </div>
      <p class="hint">{{ state.shortcutRegistered ? 'Ctrl + Alt + Z 可显示或隐藏悬浮窗，也可从系统托盘切换。' : 'Ctrl + Alt + Z 当前被其他应用占用；可使用本页开关或系统托盘。' }}</p>
    </template>
  </section>
</template>

<style scoped>
.desktop-panel { grid-column:1 / -1; scroll-margin-top:70px; border:1px solid var(--line); border-radius:var(--radius-m); padding:18px 20px; background:var(--bg-raise); }
header { display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:8px; }
h2 { margin:0; font-size:15px; color:var(--ink); }
header>span,.hint { font-size:12px; color:var(--ink-3); line-height:1.6; }
.preference-row { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:13px 0; border-bottom:1px solid var(--line); }
strong { font-size:13px; color:var(--ink); font-weight:600; }
p { margin:4px 0 0; font-size:12px; line-height:1.6; color:var(--ink-2); }
.hint { margin-top:13px; }
.switch { flex-shrink:0; width:38px; height:22px; border-radius:12px; background:var(--line-2); padding:3px; transition:background .15s; }
.switch>span { display:block; width:16px; height:16px; border-radius:50%; background:var(--bg-raise); box-shadow:0 1px 3px #0003; transition:transform .15s; }
.switch[aria-checked=true] { background:var(--amber); }
.switch[aria-checked=true]>span { transform:translateX(16px); }
button:disabled { opacity:.5; cursor:wait; }
button:focus-visible { outline:2px solid var(--amber); outline-offset:3px; }
.action { border:1px solid var(--line-2); border-radius:8px; padding:7px 11px; color:var(--ink-2); white-space:nowrap; font-size:12px; }
.error { color:var(--terra-soft); }
.error button { text-decoration:underline; }
@media(max-width:600px) { header { flex-direction:column; gap:4px; } .desktop-panel { padding:14px; } }
</style>
