<script setup lang="ts">
import { ref } from 'vue'
import { importGithubSkill, importSkillFiles, type SkillImportResult } from '../../api/settings'

const emit = defineEmits<{ imported: [] }>()
const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const files = ref<File[]>([])
const url = ref('')
const branch = ref('')
const name = ref('')
const skillPath = ref('')
const mode = ref<'upload' | 'github'>('upload')
const busy = ref(false)
const error = ref('')
const result = ref<SkillImportResult | null>(null)

async function runImport(nextMode = mode.value, reset = false): Promise<void> {
  if (busy.value) return
  if (reset) { skillPath.value = ''; result.value = null }
  mode.value = nextMode
  error.value = ''
  if (nextMode === 'github' && !url.value.trim()) { error.value = '请填写 GitHub 链接'; return }
  if (nextMode === 'upload' && !files.value.length) { error.value = '请选择技能文件或目录'; return }
  busy.value = true
  try {
    result.value = nextMode === 'github'
      ? await importGithubSkill({ url: url.value.trim(), ref: branch.value.trim() || null,
        skill_path: skillPath.value, name: name.value.trim() || null })
      : await importSkillFiles(files.value, skillPath.value, name.value)
    if (result.value.status !== 'select_skill') emit('imported')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '导入失败，请重试'
  } finally { busy.value = false }
}

function chooseFiles(event: Event): void {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return
  files.value = Array.from(input.files)
  input.value = ''
  if (files.value.length > 200 || files.value.reduce((size, file) => size + file.size, 0) > 20 * 1024 * 1024) {
    error.value = '每次最多 200 个文件，上传合计最多 20 MB'; result.value = null; return
  }
  void runImport('upload', true)
}
</script>

<template>
  <details class="skill-import">
    <summary>导入已有技能</summary>
    <div class="import-body">
      <p>支持 SKILL.md、ZIP/.skill、TAR/TGZ 或完整技能目录。也可在对话中发送 GitHub 链接或压缩包，让 AI 导入。</p>
      <label>另存名称（选填，同名时可改名）<input v-model="name" maxlength="100" :disabled="busy" placeholder="留空使用技能原名" /></label>
      <div class="import-row">
        <button type="button" :disabled="busy" @click="fileInput?.click()">选择文件 / 压缩包</button>
        <button type="button" :disabled="busy" @click="folderInput?.click()">选择技能目录</button>
        <input ref="fileInput" class="file-input" type="file" accept=".md,.zip,.skill,.tar,.gz,.tgz" :disabled="busy" @change="chooseFiles" />
        <input ref="folderInput" class="file-input" type="file" webkitdirectory multiple :disabled="busy" @change="chooseFiles" />
      </div>
      <label>GitHub 链接<input v-model="url" :disabled="busy" type="url" placeholder="https://github.com/作者/仓库/tree/main/技能目录" /></label>
      <label>分支或标签（选填；带斜杠的分支需填写完整名称）<input v-model="branch" :disabled="busy" placeholder="通常留空即可" /></label>
      <div><button type="button" :disabled="busy" @click="runImport('github', true)">从 GitHub 导入</button></div>
      <p v-if="busy" role="status">正在读取并导入技能…</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <template v-if="result?.status === 'select_skill'">
        <label>包内包含多个技能，请选择
          <select v-model="skillPath" :disabled="busy">
            <option value="" disabled>选择要导入的技能</option>
            <option v-for="candidate in result.candidates" :key="candidate.path" :value="candidate.path" :disabled="!!candidate.error">{{ candidate.name }} · {{ candidate.path }}{{ candidate.error ? `（${candidate.error}）` : '' }}</option>
          </select>
        </label>
        <p v-if="skillPath">{{ result.candidates?.find(candidate => candidate.path === skillPath)?.description }}</p>
        <div><button type="button" :disabled="busy || !skillPath" @click="runImport()">导入所选技能</button></div>
      </template>
      <div v-else-if="error && (mode === 'github' || files.length)"><button type="button" :disabled="busy" @click="runImport()">重试导入</button></div>
      <p v-if="result && result.status !== 'select_skill' && !error" role="status">{{ result.status === 'already_imported' ? '已存在，未重复导入' : '已导入' }}：{{ result.name }} · {{ result.enabled ? '可按需调用' : '已停用' }}</p>
      <p v-for="warning in result?.warnings ?? []" :key="warning">{{ warning }}</p>
      <p class="note">文件合计最多 20 MB。参考资料、脚本和模板按原目录保留；导入不会执行脚本或安装依赖。</p>
    </div>
  </details>
</template>

<style scoped>
.skill-import { border: 1px solid var(--line); border-radius: var(--radius-s); padding: 12px; background: var(--bg-app); }
summary { cursor: pointer; color: var(--ink); font-size: 13px; }
.import-body { display: flex; flex-direction: column; gap: 12px; padding-top: 12px; min-width: 0; }
p, label { font-size: 12px; line-height: 1.7; color: var(--ink-2); overflow-wrap: anywhere; }
label { display: flex; flex-direction: column; gap: 4px; }
input, select { width: 100%; min-width: 0; box-sizing: border-box; padding: 7px 9px; background: var(--bg-app); border: 1px solid var(--line-2); border-radius: var(--radius-s); color: var(--ink); font: inherit; }
input:focus-visible, select:focus-visible, button:focus-visible { outline: 2px solid var(--amber-soft); outline-offset: 2px; }
button { padding: 5px 10px; border: 1px solid var(--line-2); border-radius: var(--radius-s); background: var(--bg-app); color: var(--amber-soft); cursor: pointer; font: inherit; font-size: 12px; }
button:hover { border-color: var(--line-hover); }
button:disabled { opacity: .55; cursor: default; }
.import-row { display: flex; flex-wrap: wrap; gap: 8px; }
.file-input { display: none; }
.error { color: var(--terra-soft); }
.note { color: var(--ink-3); }
</style>
