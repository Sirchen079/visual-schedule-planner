<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import AppIcon from '../AppIcon.vue'

const props = defineProps<{ open: boolean; title: string; wide?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
watch(() => props.open, async open => {
  await nextTick()
  if (open && !dialog.value?.open) dialog.value?.showModal()
  else if (!open && dialog.value?.open) dialog.value.close()
}, { immediate: true, flush: 'post' })
onBeforeUnmount(() => dialog.value?.close())
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="guide-dialog" :class="{ wide }" :aria-label="title"
      @cancel.prevent="emit('close')" @keydown.stop @click.self="emit('close')">
      <div class="guide-frame">
        <header class="guide-header">
          <span class="guide-brand">知时 · {{ title }}</span>
          <button class="guide-close" :aria-label="`关闭${title}`" title="关闭（Esc）" @click="emit('close')"><AppIcon name="x" :size="18" /></button>
        </header>
        <slot />
      </div>
    </dialog>
  </Teleport>
</template>

<style scoped>
.guide-dialog { width:680px; max-width:calc(100vw - 32px); max-height:calc(100dvh - 48px); margin:auto; padding:0; border:1px solid var(--line-2); border-radius:12px; background:var(--bg-raise); color:var(--ink); box-shadow:var(--shadow-panel); overflow:hidden; }
.guide-dialog.wide { width:960px; }
.guide-dialog::backdrop { background:var(--overlay-backdrop); backdrop-filter:blur(3px); }
.guide-frame { display:flex; flex-direction:column; max-height:calc(100dvh - 50px); }
.guide-header { display:flex; align-items:center; justify-content:space-between; gap:16px; flex:none; padding:14px 22px; border-bottom:1px solid var(--line); }
.guide-brand { color:var(--ink-2); font-size:13px; letter-spacing:.04em; }
.guide-close { display:flex; align-items:center; justify-content:center; width:36px; height:36px; border-radius:7px; color:var(--ink-2); }
.guide-close:hover { background:var(--ink-wash); }
.guide-close:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }
@media(max-width:600px) { .guide-dialog { max-width:calc(100vw - 16px); max-height:calc(100dvh - 16px); }.guide-frame { max-height:calc(100dvh - 18px); }.guide-header { padding:10px 16px; } }
</style>
