<script setup lang="ts">
/**
 * 日记视图（/journal）：左侧历史列表 + 右侧当日（或选中日）编辑器，B×C 暗色。
 * - 保存走 PUT upsert（幂等）；删除按日；mood 预设五档（契约是自由字符串，预设只是快捷输入）
 * - 未保存切换日期前不拦（内容本地态，切换即丢）—— 保存按钮常在，等待不沉默
 * - run done 后由壳层自动刷新（App.vue 接线，覆盖 AI write_journal）
 */
import { computed, onMounted, ref, watch } from 'vue'
import DomainState from '../components/domain/DomainState.vue'
import { MOOD_PRESETS, moodLabel, useJournalStore } from '../stores/journal'
import { toIsoDate } from '../utils/date'

const journal = useJournalStore()
const todayIso = toIsoDate(new Date())

/** 编辑器本地草稿（选中日变化时从条目重置） */
const draftContent = ref('')
const draftMood = ref<string | null>(null)

function resetDraft(): void {
  draftContent.value = journal.activeEntry?.content ?? ''
  draftMood.value = journal.activeEntry?.mood ?? null
}

watch(
  () => [journal.activeDay, journal.activeEntry?.updated_at] as const,
  () => resetDraft(),
)

const dirty = computed(() => {
  if (!journal.activeEntry) return draftContent.value.trim().length > 0
  return draftContent.value !== journal.activeEntry.content || draftMood.value !== journal.activeEntry.mood
})

async function save(): Promise<void> {
  if (!journal.activeDay || journal.saving) return
  await journal.save(journal.activeDay, draftContent.value, draftMood.value)
}

async function remove(): Promise<void> {
  if (!journal.activeDay) return
  const day = journal.activeDay
  await journal.remove(day)
  if (journal.activeDay === day || !journal.activeEntry) {
    await journal.openDay(todayIso)
  }
}

function preview(content: string): string {
  const one = content.replace(/\s+/g, ' ').trim()
  return one.length > 42 ? `${one.slice(0, 42)}…` : one || '（空）'
}

onMounted(async () => {
  if (journal.entries === null) void journal.load()
  if (!journal.activeDay) await journal.openDay(todayIso)
})
</script>

<template>
  <section class="journal-view">
    <Teleport defer to="#head-actions">
      <label class="pick">
        日期
        <input
          class="pick-in"
          type="date"
          :value="journal.activeDay"
          :max="todayIso"
          aria-label="选择日记日期"
          @change="journal.openDay(($event.target as HTMLInputElement).value || todayIso)"
        />
      </label>
    </Teleport>

    <!-- 左：历史列表 -->
    <aside class="jv-side">
      <div class="jv-side-head">
        <span class="jv-caption">日记本</span>
        <span v-if="journal.entries" class="jv-count">{{ journal.entries.length }} 篇</span>
      </div>

      <DomainState
        :loading="journal.loading && journal.entries === null"
        loading-text="正在翻开日记本…"
        :error="journal.error"
        :empty="!journal.loading && journal.entries !== null && journal.entries.length === 0"
        empty-title="还没有写过"
        @retry="journal.load()"
      >
        今天写下的第一行，就是这本日记的开始。
      </DomainState>

      <ul v-if="journal.entries && journal.entries.length > 0" class="jv-list">
        <li v-for="e in journal.entries" :key="e.id">
          <button class="jv-item" :data-active="e.date === journal.activeDay" @click="journal.openDay(e.date)">
            <span class="ji-date">{{ e.date }}</span>
            <span v-if="e.mood" class="ji-mood">{{ moodLabel(e.mood) }}</span>
            <span class="ji-preview">{{ preview(e.content) }}</span>
          </button>
        </li>
      </ul>
    </aside>

    <!-- 右：编辑器 -->
    <div class="jv-editor">
      <DomainState
        :loading="journal.loadingDay"
        loading-text="正在取出这一页…"
        :error="null"
        :empty="false"
      />
      <template v-if="!journal.loadingDay && journal.activeDay">
        <header class="ed-head">
          <span class="ed-date">{{ journal.activeDay }}</span>
          <span v-if="journal.activeDay === todayIso" class="ed-today">今天</span>
          <span v-if="journal.activeEntry?.updated_at" class="ed-meta">上次保存 {{ journal.activeEntry.updated_at.slice(0, 16).replace('T', ' ') }}</span>
          <span v-if="dirty" class="ed-dirty">未保存</span>
        </header>

        <div class="mood-row">
          <span class="mood-label">心情</span>
          <button
            v-for="m in MOOD_PRESETS"
            :key="m.key"
            class="mood-chip"
            :data-on="draftMood === m.key"
            @click="draftMood = draftMood === m.key ? null : m.key"
          >
            {{ m.label }}
          </button>
        </div>

        <textarea
          v-model="draftContent"
          class="ed-text"
          placeholder="这一页留给今天。写点什么……"
          aria-label="日记内容"
        />

        <footer class="ed-foot">
          <button class="save" :disabled="journal.saving" @click="save">
            {{ journal.saving ? '保存中…' : '保存这一页' }}
          </button>
          <button v-if="journal.activeEntry?.id" class="drop" :disabled="journal.saving" @click="remove">
            删除此页
          </button>
          <span v-if="journal.actionError" class="ed-error" role="alert">{{ journal.actionError }}</span>
          <span v-else-if="journal.lastRefreshedAt && !dirty" class="ed-note">AI 写操作后自动刷新</span>
        </footer>
      </template>
    </div>
  </section>
</template>

<style scoped>
.journal-view {
  flex: 1;
  min-height: 0;
  display: flex;
}

/* 壳头日期选择 */
.pick {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--ink-3);
}
.pick-in {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-2);
  background: var(--bg-sink);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 8px;
  color-scheme: dark;
}
.pick-in:focus {
  outline: none;
  border-color: var(--line-hover);
}

/* 左列表 */
.jv-side {
  width: 292px;
  flex: none;
  border-right: 1px solid var(--line);
  padding: 18px 14px 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
}
.jv-side-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.jv-caption {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.jv-count {
  font-size: 11.5px;
  color: var(--ink-3);
}
.jv-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.jv-item {
  width: 100%;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid transparent;
  border-radius: var(--radius-s);
  padding: 8px 10px;
}
.jv-item:hover {
  background: var(--amber-wash);
}
.jv-item[data-active='true'] {
  background: var(--amber-wash);
  border-color: var(--amber-border-weak);
}
.ji-date {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--amber-dim);
}
.ji-mood {
  align-self: flex-start;
  font-size: 10.5px;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border-weak);
  border-radius: var(--radius-pill);
  padding: 0 7px;
}
.ji-preview {
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.5;
}

/* 右编辑器 */
.jv-editor {
  flex: 1;
  min-width: 0;
  padding: 18px 22px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ed-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.ed-date {
  font-family: var(--serif);
  font-size: 21px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--ink);
}
.ed-today {
  font-size: 11px;
  font-weight: 600;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border);
  border-radius: var(--radius-pill);
  padding: 1px 8px;
}
.ed-meta {
  font-size: 11.5px;
  color: var(--ink-3);
}
.ed-dirty {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--amber-soft);
}

.mood-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.mood-label {
  font-size: 12px;
  color: var(--ink-3);
  margin-right: 3px;
}
.mood-chip {
  font-size: 12px;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 3px 12px;
}
.mood-chip:hover {
  border-color: var(--line-hover);
}
.mood-chip[data-on='true'] {
  color: var(--amber-soft);
  border-color: var(--amber-border);
  background: var(--amber-wash);
  font-weight: 600;
}

.ed-text {
  flex: 1;
  min-height: 0;
  resize: none;
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.9;
  color: var(--ink);
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-m);
  padding: 16px 18px;
}
.ed-text::placeholder {
  color: var(--ink-faint);
}
.ed-text:focus {
  outline: none;
  border-color: var(--line-hover);
}

.ed-foot {
  display: flex;
  align-items: center;
  gap: 12px;
}
.save {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--btn-ok-text);
  background: var(--amber);
  border-radius: var(--radius-s);
  padding: 7px 16px;
}
.save:disabled {
  background: var(--send-idle-bg);
  color: var(--send-idle-text);
  cursor: default;
}
.drop {
  font-size: 12px;
  color: var(--terra-soft);
  border: 1px solid var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 6px 12px;
}
.drop:hover {
  border-color: var(--terra-soft);
}
.ed-error {
  font-size: 12px;
  color: var(--terra-soft);
}
.ed-note {
  font-size: 11.5px;
  color: var(--ink-3);
}
</style>
