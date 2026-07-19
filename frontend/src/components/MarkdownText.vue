<script setup>
// 轻量 Markdown 渲染：先 escape 再处理标题/粗体/列表/段落，避免引入额外依赖。
// 渲染逻辑提取自 ReportView，供报告正文、每日晨报等多处复用。
import { computed } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
})

function renderMarkdown(md) {
  if (!md) return ''
  const esc = (s) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  const out = []
  let inList = false
  const closeList = () => {
    if (inList) {
      out.push('</ul>')
      inList = false
    }
  }
  for (const raw of md.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) {
      closeList()
      continue
    }
    if (/^### /.test(line)) {
      closeList()
      out.push(`<h3>${inline(line.slice(4))}</h3>`)
    } else if (/^## /.test(line)) {
      closeList()
      out.push(`<h2>${inline(line.slice(3))}</h2>`)
    } else if (/^# /.test(line)) {
      closeList()
      out.push(`<h2>${inline(line.slice(2))}</h2>`)
    } else if (/^[-*] /.test(line)) {
      if (!inList) {
        out.push('<ul>')
        inList = true
      }
      out.push(`<li>${inline(line.slice(2))}</li>`)
    } else {
      closeList()
      out.push(`<p>${inline(line)}</p>`)
    }
  }
  closeList()
  return out.join('')
}

const html = computed(() => renderMarkdown(props.content))
</script>

<template>
  <div class="markdown" v-html="html"></div>
</template>

<style scoped>
.markdown :deep(h2) {
  font-size: 16px;
  margin: 18px 0 8px;
  color: var(--accent-strong);
}
.markdown :deep(h3) {
  font-size: 14px;
  margin: 14px 0 6px;
  color: var(--text);
}
.markdown :deep(p) {
  margin: 6px 0;
  line-height: 1.7;
  color: var(--text);
}
.markdown :deep(ul) {
  margin: 6px 0;
  padding-left: 22px;
}
.markdown :deep(li) {
  margin: 3px 0;
  line-height: 1.7;
  color: var(--text);
}
.markdown :deep(strong) {
  color: var(--text);
}
</style>
