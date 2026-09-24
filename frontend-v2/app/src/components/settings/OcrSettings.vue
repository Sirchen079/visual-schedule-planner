<script setup lang="ts">
/**
 * 设置 · 扫描件 OCR 区块：
 * - 扫描件 PDF 的逐页 OCR 模型（openai_compat 视觉端点，如硅基流动 DeepSeek-OCR）；
 *   未配置时扫描页无法识别，资料库的识别失败行会引导来这里。
 * - api_key 三态：留空提交不带字段=保留已保存密钥（后端永不回显，本表单也永不回填）；
 *   填写=替换。has_api_key=true 时徽标显示「已保存」。
 * - 加载 GET /api/settings/ocr 回填 base_url/model；保存 PUT 部分更新。
 */
import { onMounted, ref } from 'vue'
import DomainState from '../domain/DomainState.vue'
import { getOcrConfig, updateOcrConfig, type OcrConfig } from '../../api/settings'

const config = ref<OcrConfig | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const baseUrl = ref('')
const model = ref('')
const keyInput = ref('')
const saving = ref(false)
const savedNote = ref('')
const saveError = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const c = await getOcrConfig()
    config.value = c
    baseUrl.value = c.base_url
    model.value = c.model
    keyInput.value = '' // 密钥永不回填
  } catch (e) {
    error.value = e instanceof Error ? e.message : '扫描件 OCR 设置读取失败'
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (saving.value) return
  saving.value = true
  saveError.value = null
  savedNote.value = ''
  try {
    const key = keyInput.value.trim()
    // 留空 = 不带 api_key 字段（后端保留现有密钥）；填写 = 替换。清除密钥由后端空串语义预留。
    const updated = await updateOcrConfig({
      base_url: baseUrl.value.trim(),
      model: model.value.trim(),
      ...(key ? { api_key: key } : {}),
    })
    config.value = updated
    baseUrl.value = updated.base_url
    model.value = updated.model
    keyInput.value = ''
    savedNote.value = updated.has_api_key
      ? '扫描件 OCR 设置已保存'
      : '已保存；尚未配置 API Key，扫描页暂时无法识别'
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : '扫描件 OCR 设置保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(() => { void load() })
</script>

<template>
  <section id="settings-ocr" class="ocr-panel" aria-labelledby="ocr-title">
    <header class="o-head">
      <span id="ocr-title" class="o-title">扫描件 OCR</span>
      <span class="o-side">
        <span
          class="badge"
          :data-tone="config?.has_api_key ? 'ok' : undefined"
        >{{ config?.has_api_key ? '已保存' : '未配置' }}</span>
      </span>
    </header>

    <p class="f-hint">
      上传的扫描件 PDF 会逐页做 OCR 转成可检索的 Markdown。填写一个 openai 兼容的视觉模型接口；
      识别在后台进行，识别失败的文件可在资料库点「重新解析」重试。
    </p>

    <DomainState
      :loading="loading"
      loading-text="正在读取扫描件 OCR 设置…"
      :error="error"
      :empty="false"
      @retry="load()"
    />

    <form v-if="config" class="ocr-form" @submit.prevent="save">
      <p v-if="saveError" class="form-error" role="alert">{{ saveError }}</p>
      <div class="form-row">
        <label class="f-label" for="ocr-base-url">Base URL</label>
        <input
          id="ocr-base-url"
          v-model="baseUrl"
          class="t-input grow"
          placeholder="https://api.siliconflow.cn/v1"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
      <div class="form-row">
        <label class="f-label" for="ocr-model">模型</label>
        <input
          id="ocr-model"
          v-model="model"
          class="t-input grow"
          placeholder="deepseek-ai/DeepSeek-OCR"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
      <div class="form-row">
        <label class="f-label" for="ocr-api-key">API Key</label>
        <input
          id="ocr-api-key"
          v-model="keyInput"
          type="password"
          class="t-input grow"
          autocomplete="new-password"
          :placeholder="config.has_api_key ? '留空则保留已保存的密钥' : 'sk-…'"
        />
        <span v-if="config.has_api_key" class="badge" data-tone="ok">已保存</span>
      </div>
      <span class="f-hint">密钥保存在本地凭据存储、永不回显：留空提交即保留已保存的密钥，填写新值则替换。</span>
      <div class="form-row foot">
        <button id="ocr-save" type="submit" class="act" :disabled="saving">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
      <span v-if="savedNote" class="saved-note" role="status">{{ savedNote }}</span>
    </form>
  </section>
</template>

<style scoped>
/* 与设置页 .panel 同一套纸张观感（组件自带样式，不依赖父页 scoped 类） */
.ocr-panel {
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--bg-raise);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  scroll-margin-top: 76px;
}
.o-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
  padding-bottom: 8px;
}
.o-title {
  font-family: var(--serif);
  font-size: 14.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.o-side {
  display: flex;
  align-items: center;
  gap: 10px;
}
.f-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-2);
  flex: none;
}
.f-hint {
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.6;
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
.form-error {
  font-size: 12px;
  color: var(--terra-soft);
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
.badge {
  flex: none;
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
.act:disabled {
  opacity: var(--ctl-disabled-opacity, 0.5);
  cursor: default;
}
.saved-note {
  font-size: 11px;
  color: var(--ok);
}
</style>
