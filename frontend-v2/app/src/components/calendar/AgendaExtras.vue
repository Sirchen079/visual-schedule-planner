<script setup lang="ts">
import { computed } from 'vue'
import type { EventOccurrence } from '../../api/schedule'
import { occurrenceKey, occurrenceTime, occurrenceTitle } from '../../utils/eventPlacement'
const props = withDefaults(defineProps<{ items: EventOccurrence[]; paper?: boolean; showDate?: boolean }>(), { paper:true, showDate:true })
const emit = defineEmits<{ open: [item: EventOccurrence] }>()
const groups = computed(() => {
  const grouped = new Map<string, EventOccurrence[]>()
  for (const item of props.items) grouped.set(item.date, [...(grouped.get(item.date) ?? []), item])
  return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b))
})
</script>

<template>
  <details v-if="items.length" class="agenda-extras" :data-paper="paper">
    <summary><span class="extras-title">全天、截止与其他时段</span><span class="extras-count">{{ items.length }} 项</span><span class="extras-toggle" aria-hidden="true" /></summary>
    <div class="extras-list">
      <section v-for="[date, list] in groups" :key="date" class="extras-group">
        <h3 v-if="showDate">{{ Number(date.slice(5, 7)) }} 月 {{ Number(date.slice(8)) }} 日</h3>
        <button v-for="item in list" :key="occurrenceKey(item)" type="button" :title="occurrenceTitle(item)" @click="emit('open', item)">
          <span class="extras-time">{{ occurrenceTime(item) }}</span><span class="extras-name">{{ item.title }}</span><span v-if="item.task_status === 'done'" class="extras-done">已完成</span><span class="extras-arrow" aria-hidden="true">›</span>
        </button>
      </section>
    </div>
  </details>
</template>

<style scoped>
.agenda-extras { --extra-ink:var(--paper-ink); --extra-muted:var(--paper-ink-3); --extra-line:var(--paper-line); --extra-hover:var(--paper-tint); flex:none; color:var(--extra-ink); border-bottom:1px solid var(--extra-line); margin-bottom:12px; font-size:12px; }
.agenda-extras[data-paper='false'] { --extra-ink:var(--ink); --extra-muted:var(--ink-3); --extra-line:var(--line); --extra-hover:var(--bg-raise); }
summary { display:flex; align-items:center; gap:10px; padding:12px 0; cursor:pointer; list-style:none; user-select:none; }
summary::-webkit-details-marker { display:none; }
.extras-title { font-weight:500; letter-spacing:.03em; }
.extras-count { font-family:var(--mono); color:var(--extra-muted); }
.extras-toggle { margin-left:auto; color:var(--extra-muted); }
.extras-toggle::after { content:'展开 ＋'; }
[open] .extras-toggle::after { content:'收起 −'; }
.extras-list { max-height:240px; overflow:auto; padding:0 2px 12px; }
.extras-group + .extras-group { margin-top:12px; }
h3 { margin:0; padding:6px 8px; color:var(--extra-muted); font-family:var(--mono); font-size:11px; font-weight:400; }
button { display:flex; align-items:baseline; gap:12px; width:100%; text-align:left; padding:10px 8px; border-radius:7px; }
button:hover,button:focus-visible { background:var(--extra-hover); }
.extras-time { width:112px; flex:none; font-family:var(--mono); color:var(--extra-muted); font-size:11px; }
.extras-name { flex:1; min-width:0; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.extras-arrow,.extras-done { color:var(--extra-muted); }
@media(max-width:600px) { .extras-time { width:92px; } button { gap:8px; } }
</style>
