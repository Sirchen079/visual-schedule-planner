<script setup lang="ts">
/**
 * 内联 SVG 图标集合。描边使用 currentColor，继承所在组件的文字颜色。
 */
import { computed } from 'vue'

export type IconName =
  | 'today'
  | 'calendar'
  | 'board'
  | 'timeline'
  | 'habits'
  | 'journal'
  | 'ledger'
  | 'inbox'
  | 'research'
  | 'goals'
  | 'library'
  | 'reports'
  | 'trash'
  | 'settings'
  | 'plus'
  | 'more'
  | 'paperclip'
  | 'send'
  | 'stop'
  | 'chevron-down'
  | 'shield'
  | 'check'
  | 'x'
  | 'list'
  | 'alert'
  | 'spark'
  | 'bell'
  | 'timer'
  | 'chat'

const PATHS: Record<IconName, string> = {
  research: '<path d="M3 4h6a3 3 0 0 1 3 3v14a3 3 0 0 0-3-3H3zM21 4h-6a3 3 0 0 0-3 3v14a3 3 0 0 1 3-3h6z"/><path d="M6 8h3M6 11h3M15 8h3M15 11h3"/>',
  inbox: '<path d="M3 13 6 4h12l3 9v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M3 13h5l2 3h4l2-3h5"/>',
  ledger: '<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 8V5a2 2 0 0 1 2-2h13M16 11h5v5h-5a2.5 2.5 0 0 1 0-5Z"/><circle cx="17" cy="13.5" r=".6"/>',
  today:
    '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  calendar: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  board: '<rect x="4" y="4" width="5" height="12" rx="1"/><rect x="10.5" y="4" width="5" height="16" rx="1"/><rect x="17" y="4" width="3.5" height="9" rx="1"/>',
  timeline: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  habits:
    '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
  journal: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  goals: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
  library: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9"/><path d="M10 13h4"/>',
  reports:
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8M16 17H8"/>',
  trash:
    '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  settings: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/><path d="M1 14h6M9 8h6M17 16h6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  more: '<circle cx="5" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.6" fill="currentColor" stroke="none"/>',
  paperclip:
    '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
  send: '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
  stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" stroke="none"/>',
  'chevron-down': '<path d="m6 9 6 6 6-6"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
  check: '<circle cx="12" cy="12" r="9.4"/><path d="M8.4 12.3l2.5 2.5 4.9-5.2"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
  alert: '<circle cx="12" cy="12" r="9.4"/><path d="M12 7.5v5.5"/><path d="M12 16.5h.01"/>',
  spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  timer:
    '<line x1="10" x2="14" y1="2" y2="2"/><line x1="12" x2="15" y1="14" y2="11"/><circle cx="12" cy="14" r="8"/>',
  chat:
    '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
}

const props = defineProps<{ name: IconName; size?: number }>()

const inner = computed(() => PATHS[props.name] ?? '')
const px = computed(() => `${props.size ?? 19}px`)
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    :style="{ width: px, height: px }"
    v-html="inner"
  />
</template>
