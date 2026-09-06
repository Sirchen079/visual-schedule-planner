<script setup lang="ts">
import { computed } from 'vue'
import type { InputModality, ReasoningEffort } from '../../api/settings'

const contextWindow = defineModel<string | number>('contextWindow', { required: true })
const maxOutputTokens = defineModel<string | number>('maxOutputTokens', { required: true })
const inputModalities = defineModel<InputModality[]>('inputModalities', { required: true })
const props = defineProps<{ providerKind: string }>()
const reasoningEffort = defineModel<ReasoningEffort | ''>('reasoningEffort', { required: true })
const effortOptions = computed(() => [
  { value: '', label: '跟随服务商（默认）' },
  { value: 'none', label: '关闭思考（none）' },
  ...(props.providerKind === 'anthropic' ? [] : [{ value: 'minimal', label: '极低（minimal）' }]),
  { value: 'low', label: '低（low）' }, { value: 'medium', label: '中（medium）' },
  { value: 'high', label: '高（high）' }, { value: 'xhigh', label: '很高（xhigh）' },
  { value: 'max', label: '最高（max）' },
])
const modalities: { value: InputModality; label: string }[] = [
  { value: 'text', label: '文本' }, { value: 'image', label: '图片' },
  { value: 'audio', label: '音频' }, { value: 'video', label: '视频' },
]
</script>

<template>
  <div class="capabilities">
    <div class="cap-heading">模型能力</div>
    <p class="cap-hint">请以服务商说明为准，填写当前模型实际支持的能力；模型名称和模型列表不会自动设置这些值。</p>
    <div class="token-fields">
      <label class="token-field" for="config-context-window">
        <span>上下文窗口 <small>token</small></span>
        <input id="config-context-window" v-model="contextWindow" type="number" min="1024" max="10000000" step="1" placeholder="留空表示未设置" aria-describedby="context-window-hint" />
        <small id="context-window-hint">1,024–10,000,000；输入与输出共用的容量。</small>
      </label>
      <label class="token-field" for="config-max-output">
        <span>最大输出 <small>token</small></span>
        <input id="config-max-output" v-model="maxOutputTokens" type="number" min="1" max="1000000" step="1" placeholder="留空表示未设置" aria-describedby="max-output-hint" />
        <small id="max-output-hint">1–1,000,000；如设置上下文窗口，须小于该值。</small>
      </label>
    </div>
    <label class="token-field" for="config-reasoning-effort">
      <span>思考程度</span>
      <select id="config-reasoning-effort" v-model="reasoningEffort" aria-describedby="reasoning-effort-hint">
        <option v-for="option in effortOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        <option v-if="providerKind === 'anthropic' && reasoningEffort === 'minimal'" value="minimal" disabled>极低（当前协议不支持，请重新选择）</option>
      </select>
      <small id="reasoning-effort-hint">默认不指定思考参数；更高档位通常更慢，并消耗更多输出 token。可用档位取决于具体模型与服务商，请按模型说明选择。</small>
      <small v-if="providerKind === 'anthropic'">低及以上档位使用自适应思考，需要模型支持 adaptive thinking 与 effort；旧模型请保留默认。</small>
      <small v-else>使用标准 reasoning 参数；部分兼容服务不支持此参数或关闭档位，可保留默认。</small>
    </label>
    <fieldset class="modality-group" aria-describedby="modality-hint">
      <legend>支持的输入类型</legend>
      <div class="modality-options">
        <label v-for="option in modalities" :key="option.value" class="modality-option" :class="{ selected: inputModalities.includes(option.value) }">
          <input v-model="inputModalities" type="checkbox" :value="option.value" :disabled="option.value === 'text'" />
          {{ option.label }}
        </label>
      </div>
      <p id="modality-hint" class="cap-hint">AI 助手需要文本输入，必须保留文本。旧配置默认仅文本，勾选其他类型前请确认模型支持。</p>
    </fieldset>
    <p class="cap-hint route-note">模型原生支持图片时，勾选“图片”即可直接输入图片；仅支持文本的模型可通过已配置的视觉 MCP 处理图片。当前视觉 MCP 仅处理图片。原生音频仅 OpenAI Chat Completions 支持 WAV / MP3。视频能力会保存，但当前三种协议均不传递原生视频。不支持的音频或视频，请改用文字稿或关键帧图片。</p>
  </div>
</template>

<style scoped>
.capabilities { display:flex; flex-direction:column; gap:12px; border-top:1px solid var(--line-2); margin-top:4px; padding-top:14px; }
.cap-heading { font-size:13px; font-weight:600; color:var(--ink-2); }
.cap-hint { margin:0; color:var(--ink-3); font-size:12px; line-height:1.7; }
.token-fields { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; }
.token-field { display:flex; flex-direction:column; gap:7px; color:var(--ink-2); font-size:12px; }
.token-field small { font-size:11px; color:var(--ink-3); line-height:1.6; }
.token-field input, .token-field select { box-sizing:border-box; width:100%; min-width:0; background:var(--bg-app); border:1px solid var(--line-2); border-radius:var(--radius-s); color:var(--ink-1); padding:8px 10px; font:inherit; }
.modality-group { border:0; margin:0; padding:0; min-width:0; }
.modality-group legend { padding:0; margin-bottom:8px; color:var(--ink-2); font-size:12px; }
.modality-options { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:7px; }
.modality-option { display:flex; align-items:center; gap:7px; padding:7px 12px; border:1px solid var(--line-2); border-radius:var(--radius-s); color:var(--ink-2); font-size:12px; cursor:pointer; }
.modality-option.selected { border-color:var(--amber); }
.modality-option input { accent-color:var(--amber); }
.token-field input:focus-visible, .token-field select:focus-visible, .modality-option:focus-within { outline:2px solid var(--amber); outline-offset:2px; }
.route-note { border-left:2px solid var(--line-2); padding-left:10px; }
@media (max-width:600px) { .token-fields { grid-template-columns:1fr; } }
</style>
