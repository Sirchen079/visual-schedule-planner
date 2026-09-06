<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { materialTarget, searchMaterials, type MaterialSearch } from '../api/materials'
const props = defineProps<{ fileId?: number; projectId?: number }>()
const emit = defineEmits<{ indexed: [] }>()
const query = ref(''), result = ref<MaterialSearch | null>(null), error = ref(''), busy = ref(false)
let generation = 0
async function search(more = false) {
  if (busy.value) return
  const term = more ? result.value?.query ?? '' : query.value.trim()
  if (!term) return
  const offset = more ? Number(result.value?.coverage.file_offset ?? 0) + Number(result.value?.coverage.checked_files ?? 0) : 0
  const g = ++generation
  busy.value = true; error.value = ''
  try {
    const response = await searchMaterials(term, props.fileId, props.projectId, offset)
    if (g !== generation) return
    result.value = more && result.value ? { ...response, hits: [...result.value.hits, ...response.hits], errors: [...result.value.errors, ...response.errors] } : response
  } catch (e) { if (g === generation) error.value = e instanceof Error ? e.message : String(e) }
  finally { if (g === generation) { busy.value = false; emit('indexed') } }
}
watch(() => [props.fileId, props.projectId], () => { generation++; result.value = null; error.value = ''; busy.value = false })
onUnmounted(() => { generation++ })
</script>
<template>
  <section class="material-search" aria-label="检索资料正文">
    <form @submit.prevent="search()"><label>{{ fileId ? '在本材料中查找' : projectId ? '检索项目材料' : '检索资料库正文' }}<input v-model="query" placeholder="输入关键词，以空格分隔…" maxlength="200" /></label><button :disabled="busy || !query.trim()">{{ busy ? '正在检索…' : '检索正文' }}</button></form>
    <p class="hint">按本地正文关键词匹配。命中结果带有原文位置，可继续阅读全文。</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <template v-if="result">
      <p class="hint">「{{ result.query }}」· 已检查到第 {{ Number(result.coverage.file_offset) + Number(result.coverage.checked_files) }} / {{ result.coverage.total_files }} 份材料</p>
      <p v-if="!result.hits.length && !busy" class="hint">没有命中。可换更短的关键词，或打开材料按顺序阅读。</p>
      <div v-for="(hit,i) in result.hits" :key="`${hit.file_id}:${hit.part}:${i}`" class="hit"><RouterLink :to="materialTarget(hit.file_id, hit.part, hit.revision)">{{ hit.name }} · {{ hit.location }}</RouterLink><p>{{ hit.excerpt }}</p></div>
      <p v-for="(item,i) in result.errors" :key="i" class="error">材料 {{ item.file_id }}：{{ item.error }}</p>
      <button v-if="result.next_call" @click="search(true)" :disabled="busy">继续检索后续文件</button>
      <p v-if="result.coverage.candidate_limit_reached" class="hint">匹配片段较多，请限定文件或使用更具体的关键词。</p>
    </template>
  </section>
</template>
<style scoped>
.material-search { border:1px solid var(--line); border-radius:12px; padding:16px; background:var(--bg-raise); }form { display:flex; align-items:flex-end; gap:12px; flex-wrap:wrap; }label { display:flex; flex:1; min-width:180px; flex-direction:column; gap:8px; font-size:13px; color:var(--ink-2); }input { width:100%; box-sizing:border-box; padding:10px; border:1px solid var(--line-2); border-radius:7px; background:var(--bg-sink); color:var(--ink); font:inherit; }button { font:inherit; font-size:12px; border:1px solid var(--line-2); border-radius:7px; padding:10px 12px; background:var(--bg-raise); color:var(--ink); cursor:pointer; }button:disabled { opacity:.5; }.hint { color:var(--ink-3); font-size:12px; line-height:1.7; margin:10px 0; }.hit { border-top:1px solid var(--line); padding:12px 0; }a { color:var(--amber); font-size:13px; }.hit p { font-size:13px; line-height:1.8; white-space:pre-wrap; overflow-wrap:anywhere; }.error { color:var(--terra); font-size:12px; overflow-wrap:anywhere; }input:focus-visible,button:focus-visible,a:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }
</style>
