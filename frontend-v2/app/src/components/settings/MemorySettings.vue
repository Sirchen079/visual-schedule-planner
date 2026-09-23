<script setup lang="ts">
/**
 * 设置 · 长期记忆区块：
 * - 开关（默认开，后端「缺失视为开」）：关闭后 AI 的记忆工具与对话注入全部消失，文案写清后果；
 * - 记忆列表按 kind 分组：每条显示内容/来源（AI 记下 或 手动添加）/更新时间，
 *   支持行内编辑（内容+分类+检索词）、删除（两段确认防误触）、手动新增（source='user'）。
 * - 样式沿用设置页纸张变量；数据经 stores/memories（api/memories → /api/memories）。
 */
import { onMounted, reactive, ref } from 'vue'
import DomainState from '../domain/DomainState.vue'
import { useMemoriesStore } from '../../stores/memories'
import type { MemoryItem, MemoryKind } from '../../api/memories'

const store = useMemoriesStore()

const KIND_LABELS: Record<MemoryKind, string> = {
  profile: '用户画像', preference: '偏好', decision: '决定', fact: '事实', project: '项目',
}
const KIND_OPTIONS = Object.entries(KIND_LABELS) as [MemoryKind, string][]

function kindLabel(kind: string): string {
  return KIND_LABELS[kind as MemoryKind] ?? kind
}
function day(iso: string): string {
  return iso.slice(0, 10)
}

/* ---- 手动新增表单 ---- */
const formOpen = ref(false)
const form = reactive<{ kind: MemoryKind; content: string; keywords: string }>({
  kind: 'fact', content: '', keywords: '',
})
const formError = ref<string | null>(null)

async function submitForm(): Promise<void> {
  formError.value = null
  const content = form.content.trim()
  if (!content) {
    formError.value = '内容必填'
    return
  }
  if (content.length > 300) {
    formError.value = `内容过长（${content.length} 字），上限 300 字`
    return
  }
  if (await store.add({ kind: form.kind, content, keywords: form.keywords.trim() })) {
    form.content = ''
    form.keywords = ''
    formOpen.value = false
  }
}

/* ---- 行内编辑 ---- */
const editingId = ref<number | null>(null)
const edit = reactive<{ kind: MemoryKind; content: string; keywords: string }>({
  kind: 'fact', content: '', keywords: '',
})

function openEdit(item: MemoryItem): void {
  editingId.value = item.id
  edit.kind = item.kind
  edit.content = item.content
  edit.keywords = item.keywords
}

function closeEdit(): void {
  editingId.value = null
}

async function submitEdit(): Promise<void> {
  if (editingId.value === null) return
  const content = edit.content.trim()
  if (!content) {
    store.actionError = '内容必填'
    return
  }
  if (await store.edit(editingId.value, {
    kind: edit.kind, content, keywords: edit.keywords.trim(),
  })) {
    closeEdit()
  }
}

/* ---- 删除两段确认 ---- */
const confirmingDelete = ref<number | null>(null)

function removeItem(item: MemoryItem): void {
  if (confirmingDelete.value !== item.id) {
    confirmingDelete.value = item.id
    return
  }
  confirmingDelete.value = null
  void store.remove(item.id)
}

function toggleSwitch(): void {
  if (store.enabled === null || store.savingEnabled) return
  void store.toggle(!store.enabled)
}

onMounted(() => { void store.load() })
</script>

<template>
  <section id="settings-memory" class="memory-panel" aria-labelledby="memory-title">
    <header class="m-head">
      <span id="memory-title" class="m-title">长期记忆</span>
      <span class="m-side">
        <span v-if="store.items" class="m-count">{{ store.items.length }} 条</span>
        <button class="act" @click="formOpen = !formOpen">{{ formOpen ? '收起表单' : '手动添加' }}</button>
      </span>
    </header>

    <p v-if="store.actionError" class="form-error" role="alert">{{ store.actionError }}</p>

    <div class="m-toggle">
      <div>
        <span class="f-label">让 AI 记住并复用长期信息</span>
        <p class="f-hint">开启后，AI 会把你的偏好、明确决定和长期事实记成一条条记忆（默认开），并在对话时自动参考；你也可以在这里随时查看、修改或删除。</p>
        <p v-if="store.enabled === false" class="f-hint warn">已关闭：AI 不再读取或写入任何记忆，对话不会注入记忆内容；已有记忆仍保留在此，可继续查看和清理。</p>
      </div>
      <button
        id="memory-enabled-switch"
        class="switch"
        role="switch"
        aria-label="长期记忆开关"
        :aria-checked="store.enabled === true"
        :disabled="store.enabled === null || store.savingEnabled"
        @click="toggleSwitch"
      ><span></span></button>
    </div>

    <DomainState
      :loading="store.loading"
      loading-text="正在拉取记忆列表…"
      :error="store.error"
      :empty="!store.loading && store.error === null && store.items !== null && store.items.length === 0"
      empty-title="还没有记忆"
      @retry="store.load()"
    >
      AI 在对话中记下的偏好、决定和事实会出现在这里；也可以用右上角「手动添加」先写几条。
    </DomainState>

    <form v-if="formOpen" class="inline-form" @submit.prevent="submitForm">
      <p class="form-title">添加一条记忆</p>
      <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
      <div class="form-row">
        <label class="f-label" for="memory-add-kind">分类</label>
        <select id="memory-add-kind" v-model="form.kind" class="t-input">
          <option v-for="[value, label] in KIND_OPTIONS" :key="value" :value="value">{{ label }}</option>
        </select>
        <label class="f-label" for="memory-add-keywords">检索词</label>
        <input id="memory-add-keywords" v-model="form.keywords" class="t-input grow" placeholder="空格分隔，如：咖啡 偏好" />
      </div>
      <textarea
        id="memory-add-content"
        v-model="form.content"
        class="t-input area"
        placeholder="一条记忆写一个独立事实，如：用户偏好喝美式咖啡，不加糖"
      />
      <div class="form-row foot">
        <button type="submit" class="act" :disabled="store.adding">{{ store.adding ? '保存中…' : '添加' }}</button>
        <button type="button" class="act" @click="formOpen = false">取消</button>
      </div>
    </form>

    <div v-for="group in store.groupedByKind" :key="group.kind" class="m-group">
      <p class="group-title">{{ kindLabel(group.kind) }}<span class="group-count">{{ group.items.length }}</span></p>
      <ul class="items">
        <li v-for="item in group.items" :key="item.id" class="item" :data-memory-id="item.id">
          <template v-if="editingId === item.id">
            <div class="edit-box">
              <div class="form-row">
                <label class="f-label" :for="`memory-edit-kind-${item.id}`">分类</label>
                <select :id="`memory-edit-kind-${item.id}`" v-model="edit.kind" class="t-input">
                  <option v-for="[value, label] in KIND_OPTIONS" :key="value" :value="value">{{ label }}</option>
                </select>
                <label class="f-label" :for="`memory-edit-keywords-${item.id}`">检索词</label>
                <input :id="`memory-edit-keywords-${item.id}`" v-model="edit.keywords" class="t-input grow" placeholder="空格分隔" />
              </div>
              <textarea
                :id="`memory-edit-content-${item.id}`"
                v-model="edit.content"
                class="t-input area"
                aria-label="编辑记忆内容"
              />
              <div class="form-row foot">
                <button class="act" :disabled="store.busyIds.includes(item.id)" @click="submitEdit">
                  {{ store.busyIds.includes(item.id) ? '保存中…' : '保存' }}
                </button>
                <button class="act" @click="closeEdit">取消</button>
              </div>
            </div>
          </template>
          <template v-else>
            <div class="it-main">
              <span class="it-content">{{ item.content }}</span>
              <span class="it-meta">
                <span class="badge" :data-tone="item.source === 'user' ? 'ok' : undefined">{{ item.source === 'user' ? '手动添加' : 'AI 记下' }}</span>
                <span v-if="item.keywords" class="it-keywords">{{ item.keywords }}</span>
                <span>更新于 {{ day(item.updated_at) }}</span>
              </span>
            </div>
            <div class="it-acts">
              <button class="act" :disabled="store.busyIds.includes(item.id)" @click="openEdit(item)">编辑</button>
              <button
                class="act danger"
                :disabled="store.busyIds.includes(item.id)"
                @click="removeItem(item)"
              >
                {{ confirmingDelete === item.id ? '确认删除？' : '删除' }}
              </button>
              <button v-if="confirmingDelete === item.id" class="act" @click="confirmingDelete = null">取消</button>
            </div>
          </template>
        </li>
      </ul>
    </div>

    <span v-if="store.items && store.items.length > 0" class="f-hint">
      记忆按更新时间排列；AI 只会看到最近的一部分，更早的靠检索命中。删除不可恢复，请确认后再删。
    </span>
  </section>
</template>

<style scoped>
/* 与设置页 .panel 同一套纸张观感（组件自带样式，不依赖父页 scoped 类） */
.memory-panel {
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--bg-raise);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  scroll-margin-top: 76px;
}
.m-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
  padding-bottom: 8px;
}
.m-title {
  font-family: var(--serif);
  font-size: 14.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.m-side {
  display: flex;
  align-items: center;
  gap: 10px;
}
.m-count {
  font-size: 11.5px;
  color: var(--ink-3);
}
.m-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.m-toggle p {
  margin: 5px 0 0;
}
.switch {
  flex-shrink: 0;
  width: 38px;
  height: 22px;
  border-radius: 12px;
  background: var(--line-2);
  padding: 3px;
}
.switch > span {
  display: block;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--bg-raise);
  box-shadow: 0 1px 3px #0003;
  transition: transform .15s;
}
.switch[aria-checked="true"] {
  background: var(--amber);
}
.switch[aria-checked="true"] > span {
  transform: translateX(16px);
}
.switch:disabled {
  opacity: var(--ctl-disabled-opacity, 0.5);
  cursor: default;
}
.switch:focus-visible {
  outline: 2px solid var(--amber);
  outline-offset: 3px;
}
.f-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-2);
}
.f-hint {
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.6;
}
.f-hint.warn {
  color: var(--terra-soft);
}
.inline-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px dashed var(--line-2);
  border-radius: var(--radius-s);
  background: var(--bg-app);
  padding: 12px;
}
.form-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-2);
}
.form-error {
  font-size: 12px;
  color: var(--terra-soft);
}
.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.form-row.foot {
  justify-content: flex-end;
}
.t-input {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink);
  background: var(--bg-app);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 5px 9px;
}
.t-input:focus {
  outline: none;
  border-color: var(--line-hover);
}
.t-input.grow {
  flex: 1 1 200px;
  min-width: 0;
}
.t-input.area {
  width: 100%;
  min-height: 64px;
  resize: vertical;
  line-height: 1.7;
}
.m-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
  letter-spacing: 0.04em;
}
.group-count {
  margin-left: 6px;
  font-family: var(--mono);
  font-weight: 400;
  font-size: 10.5px;
  color: var(--ink-3);
}
.items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--line);
  background: var(--bg-app);
  border-radius: var(--radius-s);
  padding: 8px 11px;
}
.edit-box {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.it-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.it-content {
  font-size: 13px;
  color: var(--ink);
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.it-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}
.it-keywords::before {
  content: '#';
}
.badge {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 0 8px;
  line-height: 16px;
}
.badge[data-tone='ok'] {
  color: var(--amber-soft);
  border-color: var(--amber-border-dim);
}
.it-acts {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.act {
  flex: none;
  font-size: 11.5px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 10px;
}
.act:hover {
  border-color: var(--line-hover);
}
.act.danger {
  color: var(--terra-soft);
}
.act.danger:hover {
  border-color: var(--terra-dashed);
}
.act:disabled {
  opacity: var(--ctl-disabled-opacity, 0.5);
  cursor: default;
}
</style>
