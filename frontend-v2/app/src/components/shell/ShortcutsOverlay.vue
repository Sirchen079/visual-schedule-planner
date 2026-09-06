<script setup lang="ts">
/**
 * 快捷键速查浮层：`?` / Ctrl+/ 开关、Esc 或点击背板关闭。
 * 开关与关闭全部由 useHotkeys 的统一 keydown 分发驱动（本组件零键盘监听，
 * 守卫规则因此天然一致：输入框里按 ? 不会误开浮层）。
 * 内容直接渲染 keymap.ts 的 SHORTCUTS——与绑定同源，禁止另写一份键位文案。
 */
import { computed } from 'vue'
import AppIcon from '../AppIcon.vue'
import { GROUP_LABELS, GROUP_ORDER, SHORTCUTS } from '../../keymap'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const groups = computed(() =>
  GROUP_ORDER.map((g) => ({
    key: g,
    label: GROUP_LABELS[g],
    items: SHORTCUTS.filter((s) => s.group === g),
  })),
)
</script>

<template>
  <Teleport to="body">
    <div v-if="props.open" class="sc-backdrop" @click.self="emit('close')">
      <div class="sc-card" role="dialog" aria-modal="true" aria-label="键盘快捷键">
        <header class="sc-head">
          <span class="sc-title">键盘快捷键</span>
          <button class="sc-close" title="关闭（Esc）" aria-label="关闭速查浮层" @click="emit('close')">
            <AppIcon name="x" :size="14" />
          </button>
        </header>

        <section v-for="g in groups" :key="g.key" class="sc-group">
          <h3 class="sc-cap">{{ g.label }}</h3>
          <ul class="sc-list">
            <li v-for="item in g.items" :key="item.id" class="sc-row">
              <kbd class="sc-keys">{{ item.keys }}</kbd>
              <span class="sc-desc">{{ item.desc }}</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.sc-backdrop {
  position: fixed;
  inset: 0;
  z-index: 70; /* 盖过通知面板(40/41)与事件详情卡(60)：Esc 分层的第①层在最内视觉层之上 */
  background: var(--overlay-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
}
.sc-card {
  width: 560px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 88px);
  overflow-y: auto;
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-l);
  box-shadow: var(--shadow-panel);
  padding: 12px 22px 14px;
}
.sc-head {
  display: flex;
  align-items: center;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
.sc-title {
  font-family: var(--serif);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.04em;
}
.sc-close {
  margin-left: auto;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-s);
  color: var(--ink-3);
}
.sc-close:hover {
  background: var(--ink-wash);
  color: var(--ink-2);
}

.sc-group {
  margin-top: 10px;
}
.sc-cap {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.16em;
  color: var(--amber-soft);
  margin-bottom: 4px;
}
.sc-list {
  display: flex;
  flex-direction: column;
}
.sc-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 2.5px 0;
  font-size: 12.5px;
  line-height: 1.55;
}
.sc-keys {
  flex: none;
  min-width: 86px;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-2);
  background: var(--bg-sink);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 1px 8px;
  text-align: center;
  white-space: nowrap;
}
.sc-desc {
  color: var(--ink-2);
}
</style>
