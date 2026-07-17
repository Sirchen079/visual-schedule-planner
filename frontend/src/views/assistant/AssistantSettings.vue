<script setup>
// 设置区：模型配置 / 人设 / Skill / 高级选项 四组手风琴折叠（details），默认展开第一组。
// configForm / skillForm 是父组件持有的表单对象，此处直接双向绑定其字段（对象引用不变，数据流不变），
// 所有保存/启用/导入等动作一律 emit 给 AssistantView 执行。
import ArtIcon from '../../components/ArtIcon.vue'

defineProps({
  configs: { type: Array, default: () => [] },
  activeConfig: { type: Object, default: null },
  configForm: { type: Object, required: true },
  canSaveConfig: { type: Boolean, default: false },
  hasConfig: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  modelOptions: { type: Array, default: () => [] },
  modelLoading: { type: Boolean, default: false },
  skills: { type: Array, default: () => [] },
  selectedSkillId: { type: [Number, String], default: null },
  activeSkillId: { type: [Number, String], default: null },
  skillForm: { type: Object, required: true },
  canSaveSkill: { type: Boolean, default: false },
})
defineEmits([
  'new-config',
  'select-config',
  'save-config',
  'test-config',
  'enable-config',
  'fetch-models',
  'new-skill',
  'select-skill',
  'save-skill',
  'enable-skill',
  'import-skill',
])
</script>

<template>
  <div class="assistant-settings">
    <details class="card settings-group" open>
      <summary>
        <span class="group-copy">
          <span class="group-title">模型配置</span>
          <span class="group-hint muted">Provider、模型与 API Key；key 只保存在本地后端数据库。</span>
        </span>
        <ArtIcon name="chevron-right" tone="pearl" :size="16" class="group-chevron" />
      </summary>
      <div class="group-body">
        <div class="panel-title">
          <p class="muted">选择已有配置，或新建一套连接参数。</p>
          <button class="ghost compact" @click="$emit('new-config')">新建</button>
        </div>

        <div v-if="configs.length" class="pill-list">
          <button
            v-for="config in configs"
            :key="config.id"
            class="ghost pill"
            :class="{ active: activeConfig?.id === config.id, enabled: config.enabled }"
            @click="$emit('select-config', config)"
          >
            {{ config.name }}
          </button>
        </div>

        <div class="form-grid">
          <label>
            <span>配置名称</span>
            <input v-model="configForm.name" placeholder="默认配置" />
          </label>
          <label>
            <span>Provider</span>
            <select v-model="configForm.provider">
              <option value="openai_chat">OpenAI Chat Completions</option>
              <option value="openai_responses">OpenAI Responses</option>
              <option value="claude_messages">Claude Messages</option>
            </select>
          </label>
          <label>
            <span>模型</span>
            <div class="model-picker">
              <input v-model="configForm.model" placeholder="点击获取模型，或手动填写模型 ID" />
              <button class="ghost compact" :disabled="modelLoading || busy" @click="$emit('fetch-models')">
                {{ modelLoading ? '获取中' : '获取模型' }}
              </button>
            </div>
            <select
              v-if="modelOptions.length"
              v-model="configForm.model"
              class="model-select"
            >
              <option value="">选择模型</option>
              <option v-for="model in modelOptions" :key="model" :value="model">
                {{ model }}
              </option>
            </select>
          </label>
          <label>
            <span>API Key</span>
            <input v-model="configForm.api_key" type="password" placeholder="留空表示不修改" />
          </label>
        </div>

        <div class="panel-actions">
          <button :disabled="!canSaveConfig || busy" @click="$emit('save-config')">保存并启用</button>
          <button class="ghost" :disabled="!hasConfig || busy" @click="$emit('test-config')">测试连接</button>
          <button v-if="activeConfig && !activeConfig.enabled" class="ghost" :disabled="busy" @click="$emit('enable-config', activeConfig)">
            仅启用
          </button>
        </div>
      </div>
    </details>

    <details class="card settings-group">
      <summary>
        <span class="group-copy">
          <span class="group-title">人设</span>
          <span class="group-hint muted">为空时使用内置幕僚式默认人设，和 skill 工作规则分开。</span>
        </span>
        <ArtIcon name="chevron-right" tone="pearl" :size="16" class="group-chevron" />
      </summary>
      <div class="group-body">
        <div class="form-grid">
          <label>
            <span>助手名称</span>
            <input v-model="configForm.assistant_name" placeholder="知时助手" />
          </label>
          <label>
            <span>自定义人设</span>
            <textarea
              v-model="configForm.persona"
              class="persona-input"
              placeholder="可选；留空使用内置默认人设"
            ></textarea>
          </label>
        </div>
        <div class="panel-actions">
          <button :disabled="!canSaveConfig || busy" @click="$emit('save-config')">保存人设与配置</button>
        </div>
      </div>
    </details>

    <details class="card settings-group">
      <summary>
        <span class="group-copy">
          <span class="group-title">Skill 规则</span>
          <span class="group-hint muted">skill 只保存工作规则，和助手人设分开。</span>
        </span>
        <ArtIcon name="chevron-right" tone="pearl" :size="16" class="group-chevron" />
      </summary>
      <div class="group-body">
        <div class="panel-title">
          <p class="muted">选择已有 skill，或导入 .md / .txt 文件。</p>
          <button class="ghost compact" @click="$emit('import-skill')">导入</button>
        </div>

        <div v-if="skills.length" class="pill-list">
          <button
            v-for="skill in skills"
            :key="skill.id"
            class="ghost pill"
            :class="{ active: selectedSkillId === skill.id, enabled: activeSkillId === skill.id || skill.enabled }"
            @click="$emit('select-skill', skill)"
          >
            {{ skill.name }}
          </button>
        </div>

        <div class="skill-tools">
          <button class="ghost compact" @click="$emit('new-skill')">新建 skill</button>
          <button
            v-if="selectedSkillId"
            class="ghost compact"
            :disabled="busy || activeSkillId === selectedSkillId"
            @click="$emit('enable-skill', skills.find((s) => s.id === selectedSkillId))"
          >
            启用当前
          </button>
        </div>

        <div class="form-grid">
          <label>
            <span>名称</span>
            <input v-model="skillForm.name" placeholder="论文规划 / 每周复盘" />
          </label>
          <label>
            <span>描述</span>
            <input v-model="skillForm.description" placeholder="这个 skill 适合什么工作流" />
          </label>
          <label>
            <span>正文</span>
            <textarea
              v-model="skillForm.content"
              class="skill-input"
              placeholder="写入助手规则、任务拆解方法、资料整理偏好..."
            ></textarea>
          </label>
        </div>

        <div class="panel-actions">
          <button :disabled="!canSaveSkill || busy" @click="$emit('save-skill')">保存并启用 skill</button>
        </div>
      </div>
    </details>

    <details class="card settings-group">
      <summary>
        <span class="group-copy">
          <span class="group-title">高级选项</span>
          <span class="group-hint muted">Base URL、代理、请求头与联网搜索，随模型配置一起保存。</span>
        </span>
        <ArtIcon name="chevron-right" tone="pearl" :size="16" class="group-chevron" />
      </summary>
      <div class="group-body">
        <div class="form-grid">
          <label>
            <span>Base URL</span>
            <input v-model="configForm.base_url" placeholder="可选" />
          </label>
          <label>
            <span>完整 URL</span>
            <input v-model="configForm.full_url" placeholder="可选，优先于 Base URL" />
          </label>
          <label>
            <span>HTTP Proxy</span>
            <input v-model="configForm.proxy_url" placeholder="可选，例如 http://127.0.0.1:7890" />
          </label>
          <label>
            <span>额外 Headers</span>
            <textarea v-model="configForm.extra_headers_text" class="headers-input" spellcheck="false"></textarea>
          </label>
          <label class="check-field">
            <input v-model="configForm.native_web_search_enabled" type="checkbox" />
            <span class="check-copy">
              <strong>启用模型原生联网搜索</strong>
              <small>由模型接口自身执行搜索；适合 Kimi Code、Claude 或 OpenAI 的内置联网能力。</small>
            </span>
          </label>
          <label class="check-field">
            <input v-model="configForm.search_enhancement_enabled" type="checkbox" />
            <span class="check-copy">
              <strong>搜索增强</strong>
              <small>要求助手先用原生联网搜索查找参考资料，再结合本地任务和资料进行规划。</small>
            </span>
          </label>
          <label
            v-if="configForm.native_web_search_enabled || configForm.search_enhancement_enabled"
            class="wide-field"
          >
            <span>原生联网参数 JSON</span>
            <textarea
              v-model="configForm.native_web_search_options_text"
              class="headers-input native-options-input"
              spellcheck="false"
              placeholder='可选。例如 OpenAI Chat: {"web_search_options":{"search_context_size":"low"}}'
            ></textarea>
          </label>
        </div>
        <div class="panel-actions">
          <button :disabled="!canSaveConfig || busy" @click="$emit('save-config')">保存并启用</button>
        </div>
      </div>
    </details>
  </div>
</template>

<style scoped>
/* 手风琴分组：卡片无内边距，summary 整行可点；表单样式复用 AssistantView 集中维护的类 */
.settings-group {
  padding: 0;
  overflow: hidden;
  background: var(--surface);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.settings-group summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 16px;
  cursor: pointer;
  list-style: none;
  font-size: 14px;
}

.settings-group summary::-webkit-details-marker {
  display: none;
}

.group-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.group-title {
  color: var(--text);
  font-size: 15px;
  font-weight: 800;
}

.group-chevron {
  flex-shrink: 0;
  transition: transform 0.18s ease;
}

.settings-group[open] .group-chevron {
  transform: rotate(90deg);
}

.group-body {
  padding: 0 16px 16px;
}
</style>
