<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { materialTarget, readMaterial, type MaterialRead } from '../api/materials'
import MaterialSearch from './MaterialSearch.vue'
const props = defineProps<{ fileId: number; part?: number; revision?: string }>()
const emit = defineEmits<{ indexed: [] }>()
const router = useRouter(), data = ref<MaterialRead | null>(null), loading = ref(false), error = ref(''), jump = ref(1)
let generation = 0
const start = computed(() => data.value?.parts[0]?.part ?? props.part ?? 1)
const end = computed(() => data.value?.parts[data.value.parts.length-1]?.part ?? start.value)
async function load(ignoreRevision = false) {
  const g = ++generation
  loading.value = true; error.value = ''; data.value = null
  try {
    const result = await readMaterial(props.fileId, ignoreRevision ? 1 : props.part ?? 1, ignoreRevision ? undefined : props.revision)
    if (g !== generation) return
    data.value = result; jump.value = result.parts[0]?.part ?? 1
    if (ignoreRevision) void router.replace(materialTarget(props.fileId, 1, result.document.revision))
  } catch (e) { if (g === generation) error.value = e instanceof Error ? e.message : String(e) }
  finally { if (g === generation) { loading.value = false; emit('indexed') } }
}
function navigate(part: number) {
  if (!data.value) return
  void router.push(materialTarget(props.fileId, Math.max(1, Math.min(part, data.value.document.total_parts)), data.value.document.revision))
}
watch(() => [props.fileId, props.part, props.revision], () => { void load() }, { immediate:true })
onUnmounted(() => { generation++ })
</script>
<template>
  <article class="material-reader" aria-label="材料原文">
    <header><h2>{{ data?.document.name || '阅读材料' }}</h2><RouterLink to="/library">收起阅读</RouterLink></header>
    <p v-if="loading" role="status">正在读取原文…</p>
    <p v-if="error" class="error" role="alert">{{ error }} <button @click="load(true)">从最新版本重新读取</button></p>
    <template v-if="data">
      <p class="hint">{{ data.document.indexed_chars.toLocaleString() }} 字符 · {{ data.document.total_parts }} 个片段 · 当前展示 {{ start }}–{{ end }}</p>
      <p v-if="data.document.partial" class="warning">此处仅覆盖已保存的内容，材料的完整性尚未确认。</p>
      <p v-for="(warning,i) in data.document.warnings" :key="i" class="warning">{{ warning }}</p>
      <MaterialSearch :file-id="fileId" />
      <section v-for="part in data.parts" :key="part.part" class="part"><h3>{{ part.location }} <span>片段 {{ part.part }}</span></h3><pre>{{ part.text }}</pre></section>
      <nav aria-label="原文分页"><button @click="navigate(start-3)" :disabled="loading || start <= 1">上一组片段</button><form @submit.prevent="navigate(jump)"><label>跳至片段<input v-model.number="jump" type="number" :min="1" :max="data.document.total_parts" required /></label><button :disabled="loading">跳转</button></form><button @click="navigate(end+1)" :disabled="loading || !data.next_call">继续阅读</button></nav>
      <p class="hint">原文中的页码、行号或字符区间便于核对。这里只展示当前片段；扫描页和超过解析容量的内容会明确提示。</p>
    </template>
  </article>
</template>
<style scoped>
.material-reader { color:var(--ink); border:1px solid var(--line-2); border-radius:12px; padding:20px; background:var(--bg-raise); }header,nav,nav form { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }h2 { font-size:18px; margin:0; overflow-wrap:anywhere; }a { font-size:12px; color:var(--amber); }.hint { font-size:12px; color:var(--ink-3); line-height:1.7; }.warning,.error { font-size:13px; color:var(--terra-soft); line-height:1.7; overflow-wrap:anywhere; }.part { border-top:1px solid var(--line); margin-top:18px; padding-top:12px; }h3 { font-size:13px; color:var(--amber); }h3 span { color:var(--ink-3); margin-left:8px; font-weight:400; }pre { font:14px/1.9 var(--sans); white-space:pre-wrap; overflow-wrap:anywhere; padding:14px; border-radius:8px; background:var(--bg-sink); margin:10px 0 20px; }button,input { font:inherit; color:var(--ink); background:var(--bg-raise); border:1px solid var(--line-2); border-radius:7px; padding:8px 10px; }button { font-size:12px; cursor:pointer; }button:disabled { opacity:.5; }nav label { font-size:12px; color:var(--ink-3); }nav input { width:60px; margin-left:8px; }button:focus-visible,input:focus-visible,a:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }
</style>
