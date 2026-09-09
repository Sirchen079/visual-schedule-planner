<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../../utils/md'

const props = defineProps<{ content: string }>()
// A streamed delta changes only its own message; saved formulas keep their render.
const html = computed(() => renderMarkdown(props.content))
</script>

<template><div class="markdown-content" v-html="html" /></template>
