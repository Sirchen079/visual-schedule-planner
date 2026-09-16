<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{ open: boolean; label: string }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
function trapFocus(event: KeyboardEvent) {
  const elements = [...(dialog.value?.querySelectorAll<HTMLElement>('button, a[href], input, select, textarea, summary, [tabindex="0"]') ?? [])]
    .filter(element => !element.matches(':disabled') && element.checkVisibility())
  const first = elements[0], last = elements[elements.length - 1]
  if (!first) { event.preventDefault(); return }
  if (event.shiftKey && (document.activeElement === first || !dialog.value?.contains(document.activeElement))) {
    event.preventDefault(); last?.focus()
  } else if (!event.shiftKey && (document.activeElement === last || !dialog.value?.contains(document.activeElement))) {
    event.preventDefault(); first.focus()
  }
}
watch(() => props.open, async open => {
  await nextTick()
  if (open && props.open && !dialog.value?.open) dialog.value?.showModal()
  else if (!props.open) dialog.value?.close()
}, { immediate: true })
onBeforeUnmount(() => dialog.value?.close())
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="detail-dialog" :aria-label="label" @cancel.prevent="emit('close')" @click.self="emit('close')" @keydown.esc.stop.prevent="emit('close')" @keydown.tab="trapFocus">
      <div class="detail-inner">
        <header class="detail-header"><span>{{ label }}</span><button type="button" aria-label="关闭详情" autofocus @click="emit('close')">×</button></header>
        <div class="detail-body"><slot /></div>
      </div>
    </dialog>
  </Teleport>
</template>

<style scoped>
.detail-dialog { padding:0; width:600px; max-width:calc(100vw - 32px); max-height:calc(100dvh - 48px); margin:auto; border:1px solid var(--paper-line); border-radius:12px; background:var(--paper-bg); color:var(--paper-ink); box-shadow:0 16px 64px #0004; overflow:auto; }
.detail-dialog::backdrop { background:var(--paper-backdrop); backdrop-filter:blur(3px); }
.detail-inner { min-width:0; }
.detail-header { position:sticky; top:0; z-index:1; display:flex; justify-content:space-between; align-items:center; padding:12px 24px; border-bottom:1px solid var(--paper-line); background:var(--paper-bg); color:var(--paper-ink-3); font-size:12px; letter-spacing:.08em; }
.detail-header button { width:32px; height:32px; border:1px solid transparent; border-radius:7px; font-size:23px; line-height:1; color:var(--paper-ink-2); }
.detail-header button:hover { background:var(--paper-tint); border-color:var(--paper-line); }
.detail-body { padding:24px; overflow-wrap:anywhere; }
@media(max-width:600px) { .detail-dialog { max-height:calc(100dvh - 24px); } .detail-body { padding:18px; } .detail-header { padding:10px 18px; } }
</style>
