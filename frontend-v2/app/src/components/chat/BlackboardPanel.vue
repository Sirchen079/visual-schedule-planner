<script setup lang="ts">
/**
 * 「黑板」面板：AI 用 show_blackboard 工具推送的自包含 HTML 示意页。
 * 内容在 sandbox iframe 里渲染（仅 allow-scripts、无同源）——页面内脚本拿不到
 * 应用会话、接口与存储，也与新窗口/表单/顶层导航隔离。消息流 v-html 通道禁
 * iframe，黑板是独立的展示通道，互不影响。
 */
import { ref, watch } from 'vue'
import { useRunStore } from '../../stores/run'

const run = useRunStore()
const collapsed = ref(false)
/** 手动收起后，同一页内容微调不再自动弹开；换新页（内容变化）才重新展开 */
const dismissedFor = ref('')
watch(() => run.blackboard, (page) => {
  if (page && dismissedFor.value !== page.html) collapsed.value = false
})

function collapse() {
  collapsed.value = true
  if (run.blackboard) dismissedFor.value = run.blackboard.html
}
</script>

<template>
  <section v-if="run.blackboard" class="blackboard" :data-collapsed="collapsed ? '' : null">
    <header class="bb-head">
      <span class="bb-tag">黑板</span>
      <span class="bb-title">{{ run.blackboard.title }}</span>
      <button class="bb-btn" type="button" @click="collapsed ? (collapsed = false) : collapse()">
        {{ collapsed ? '展开' : '收起' }}
      </button>
    </header>
    <iframe
      v-if="!collapsed"
      class="bb-frame"
      sandbox="allow-scripts"
      :srcdoc="run.blackboard.html"
      :title="`AI 黑板 · ${run.blackboard.title}`"
    />
  </section>
</template>

<style scoped>
.blackboard {
  flex: none;
  margin: 10px 18px 0;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--bg-raise);
  overflow: hidden;
}
.bb-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
}
.bb-tag {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 2px 8px;
}
.bb-title {
  min-width: 0;
  font-family: var(--serif);
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bb-btn {
  margin-left: auto;
  flex: none;
  font-size: 12px;
  color: var(--ink-3);
  border-radius: 6px;
  padding: 3px 9px;
}
.bb-btn:hover { background: var(--ink-wash); color: var(--ink-2); }
.bb-frame {
  display: block;
  width: 100%;
  height: min(46vh, 420px);
  border: 0;
  border-top: 1px solid var(--line);
  background: #fff;
}
.blackboard[data-collapsed] .bb-head { padding-bottom: 8px; }
</style>
