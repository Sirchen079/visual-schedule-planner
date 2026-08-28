<script setup>
// 阶段 D1：工具「始终允许」授权管理面板。
// 列出已创建的 grant（工具名 + 创建时间 + 删除），下方权限档位选择器（careful/standard/autonomous）。
// 展开时拉取 grant 列表 + 当前 agent_autonomy 设置；删除走二次确认。
import { ref, onMounted } from 'vue'
import { listAiGrants, deleteAiGrant } from '../../api/ai'
import { getSettings, updateSettings } from '../../api/settings'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import ArtIcon from '../../components/ArtIcon.vue'

const grants = ref([])
const loading = ref(false)
const error = ref('')
const autonomy = ref('standard')
const pendingDelete = ref(null) // 待删除的 grant（触发二次确认）

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [g, s] = await Promise.all([listAiGrants(), getSettings()])
    grants.value = Array.isArray(g) ? g : []
    autonomy.value = s.agent_autonomy || 'standard'
  } catch (err) {
    error.value = err?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function doDelete() {
  const g = pendingDelete.value
  pendingDelete.value = null
  if (!g) return
  try {
    await deleteAiGrant(g.id)
    grants.value = grants.value.filter((x) => x.id !== g.id)
  } catch (err) {
    error.value = err?.message || '删除失败'
  }
}

async function changeAutonomy(level) {
  autonomy.value = level
  try {
    await updateSettings({ agent_autonomy: level })
  } catch (err) {
    error.value = err?.message || '保存档位失败'
  }
}

function fmtDate(s) {
  if (!s) return ''
  try {
    return new Date(s).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

onMounted(load)
</script>

<template>
  <div class="grants-panel">
    <!-- 权限档位选择器 -->
    <section class="autonomy-section">
      <h4>权限档位</h4>
      <p class="hint">控制助手执行写操作前的询问粒度。</p>
      <div class="autonomy-options">
        <label class="autonomy-opt" :class="{ active: autonomy === 'careful' }">
          <input type="radio" value="careful" v-model="autonomy" @change="changeAutonomy('careful')" />
          <div class="opt-copy">
            <strong>谨慎</strong>
            <small>所有写操作都先问</small>
          </div>
        </label>
        <label class="autonomy-opt" :class="{ active: autonomy === 'standard' }">
          <input type="radio" value="standard" v-model="autonomy" @change="changeAutonomy('standard')" />
          <div class="opt-copy">
            <strong>标准（默认）</strong>
            <small>询问，但「以后都允许」生效</small>
          </div>
        </label>
        <label class="autonomy-opt" :class="{ active: autonomy === 'autonomous' }">
          <input type="radio" value="autonomous" v-model="autonomy" @change="changeAutonomy('autonomous')" />
          <div class="opt-copy">
            <strong>自主</strong>
            <small>除清空回收站、批量删除、导入联网资料外不再询问</small>
          </div>
        </label>
      </div>
    </section>

    <!-- grant 列表 -->
    <section class="grants-list-section">
      <h4>已授权工具</h4>
      <p class="hint">以下工具已被「以后都允许」，执行时不再弹确认卡。在确认卡片勾选「以后都允许」即可加入。</p>
      <p v-if="loading" class="muted">加载中…</p>
      <p v-else-if="error" class="error">{{ error }}</p>
      <ul v-else-if="grants.length" class="grants-list">
        <li v-for="g in grants" :key="g.id" class="grant-item">
          <div class="grant-copy">
            <strong class="grant-tool">{{ g.tool_name }}</strong>
            <small v-if="g.arg_pattern" class="grant-pattern">参数约束：{{ g.arg_pattern }}</small>
            <small class="grant-date">{{ fmtDate(g.created_at) }}</small>
          </div>
          <button class="ghost compact danger" @click="pendingDelete = g" title="删除授权规则">
            <ArtIcon name="close" tone="pearl" :size="14" />
            <span>移除</span>
          </button>
        </li>
      </ul>
      <p v-else class="empty">还没有授权规则。下次确认危险操作时勾选「以后都允许」即可。</p>
    </section>

    <ConfirmDialog
      :open="!!pendingDelete"
      title="移除授权规则？"
      :message="pendingDelete ? `移除后，调用 ${pendingDelete.tool_name} 时将恢复确认。` : ''"
      confirm-text="移除"
      danger
      @confirm="doDelete"
      @cancel="pendingDelete = null"
    />
  </div>
</template>

<style scoped>
.grants-panel {
  display: grid;
  gap: 16px;
}

.autonomy-section h4,
.grants-list-section h4 {
  margin: 0 0 4px;
  font-size: 13px;
  color: var(--text);
}

.hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text-soft);
}

.autonomy-options {
  display: grid;
  gap: 8px;
}

.autonomy-opt {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.autonomy-opt.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, var(--surface-2));
}

.autonomy-opt input {
  margin-top: 3px;
}

.opt-copy {
  display: grid;
  gap: 2px;
}

.opt-copy strong {
  font-size: 13px;
  color: var(--text);
}

.opt-copy small {
  font-size: 11px;
  color: var(--text-soft);
}

.grants-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.grant-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.grant-copy {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
}

.grant-tool {
  font-size: 13px;
  color: var(--text);
  font-family: var(--font-mono, monospace);
}

.grant-pattern {
  font-size: 11px;
  color: var(--text-soft);
}

.grant-date {
  font-size: 10px;
  color: var(--text-muted);
}

.empty {
  padding: 16px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
}

.error {
  color: var(--danger);
  font-size: 12px;
}

.muted {
  color: var(--text-muted);
  font-size: 12px;
}
</style>
