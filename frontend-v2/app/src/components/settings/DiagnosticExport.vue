<script setup lang="ts">
import { ref } from 'vue'

const busy = ref(false)
const error = ref('')
const downloaded = ref(false)
async function exportLogs() {
  if (busy.value) return
  busy.value = true; error.value = ''; downloaded.value = false
  try {
    const response = await fetch('/api/diagnostics/export', { cache: 'no-store' })
    if (!response.ok) throw new Error('日志导出失败，请稍后重试。')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || 'zhishi-diagnostics.zip'
    document.body.append(link); link.click(); link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    downloaded.value = true
  } catch { error.value = '日志导出失败，请确认知时服务正在运行后重试。' }
  finally { busy.value = false }
}
</script>

<template>
  <section id="settings-diagnostics" class="diagnostics" aria-labelledby="diagnostics-title">
    <div><h2 id="diagnostics-title">诊断日志</h2>
      <p>遇到软件问题时，导出日志并附在问题反馈中，帮助定位发生原因。</p>
      <p class="privacy">日志将自动脱敏后再导出；个人数据全程保存在本地，本功能不会自动上传。</p>
      <p class="hint">记录近期运行状态、错误位置、接口耗时与 AI 缓存用量，不含密钥、聊天正文和附件内容。反馈时请一并说明发生时间和操作步骤。</p>
    </div>
    <button :disabled="busy" @click="exportLogs">{{ busy ? '正在导出…' : '导出诊断日志' }}</button>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="downloaded" class="result" role="status">已发起日志下载。请将保存的 ZIP 文件附在问题反馈中。</p>
  </section>
</template>

<style scoped>
.diagnostics { scroll-margin-top:100px; }
.diagnostics { grid-column:1 / -1; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:16px; border:1px solid var(--line); border-radius:var(--radius-m); padding:18px 20px; background:var(--bg-raise); }
.diagnostics>div { flex:1; min-width:220px; }
h2 { margin:0 0 8px; font-size:15px; color:var(--ink); }
p { margin:5px 0 0; font-size:12px; line-height:1.7; color:var(--ink-2); }
.privacy { color:var(--ink); }
.hint { color:var(--ink-3); }
button { border:1px solid var(--line-2); border-radius:8px; padding:9px 13px; color:var(--ink); white-space:nowrap; font-size:12px; }
button:disabled { opacity:.5; cursor:wait; }
button:focus-visible { outline:2px solid var(--amber); outline-offset:3px; }
.error,.result { flex-basis:100%; }
.error { color:var(--terra-soft); }
@media(max-width:600px) { .diagnostics { padding:14px; } }
</style>
