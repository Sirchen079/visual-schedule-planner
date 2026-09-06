<script setup lang="ts">
defineProps<{ prominent?: boolean }>()
</script>

<template>
  <a class="project-link" :class="{ prominent }" href="https://github.com/Sirchen079/visual-schedule-planner"
     target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"
     title="喜欢知时？到 GitHub 点个 Star" aria-label="打开知时 GitHub 仓库，喜欢的话点个 Star">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 2.8 5.7 6.3.9-4.55 4.44 1.07 6.26L12 17.35l-5.62 2.95 1.07-6.26L2.9 9.6l6.3-.9z" /></svg>
    <span>{{ prominent ? '喜欢知时？点个 Star' : 'GitHub · Star' }}</span>
    <span aria-hidden="true">↗</span>
  </a>
</template>

<style scoped>
.project-link { display:inline-flex; flex:none; align-items:center; justify-content:center; gap:6px; padding:5px 9px; border:1px solid var(--amber-border); border-radius:7px; background:var(--amber-wash); color:var(--amber-soft); font-size:12px; line-height:16px; white-space:nowrap; text-decoration:none; }
.project-link:hover { background:var(--amber-wash-strong); border-color:var(--amber-soft); }
.project-link:focus-visible { outline:2px solid var(--amber); outline-offset:3px; }
.project-link.prominent { padding:10px 14px; font-size:13px; }
</style>
