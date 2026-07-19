<script setup>
// 通用右键菜单：fixed 定位 + Teleport 到 body（避免祖先 transform/overflow 影响定位与裁切）。
// 点击外部 / Esc / 滚动 / 窗口缩放时关闭；渲染后自动夹紧在视口内。
// items: { key, label, icon?, danger?, active?, children? } 或 { separator: true }；children 为一级悬停子菜单。
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import ArtIcon from './ArtIcon.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  x: { type: Number, default: 0 },
  y: { type: Number, default: 0 },
  items: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'select'])

const root = ref(null)
const subRoot = ref(null)
const ready = ref(false)
const pos = ref({ left: 0, top: 0 })
const openSub = ref(null) // 当前展开子菜单的父项 key
const subItems = ref([])
const subPos = ref({ left: 0, top: 0 })

watch(
  () => props.open,
  async (v) => {
    if (!v) {
      detach()
      openSub.value = null
      ready.value = false
      return
    }
    ready.value = false
    openSub.value = null
    pos.value = { left: props.x, top: props.y }
    await nextTick()
    clampMain()
    ready.value = true
    window.addEventListener('mousedown', onOutsideDown, true)
    window.addEventListener('keydown', onKeydown, true)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
  }
)

onBeforeUnmount(detach)

function detach() {
  window.removeEventListener('mousedown', onOutsideDown, true)
  window.removeEventListener('keydown', onKeydown, true)
  window.removeEventListener('scroll', close, true)
  window.removeEventListener('resize', close)
}

function clampMain() {
  const el = root.value
  if (!el) return
  const r = el.getBoundingClientRect()
  let { left, top } = pos.value
  if (left + r.width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - r.width - 8)
  if (top + r.height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - r.height - 8)
  pos.value = { left, top }
}

function close() {
  emit('close')
}

function onOutsideDown(e) {
  if (root.value && !root.value.contains(e.target)) close()
}

function onKeydown(e) {
  if (e.key !== 'Escape') return
  e.stopPropagation()
  e.preventDefault()
  close()
}

// 悬停父项：展开子菜单（叶子项悬停则收起）；子菜单贴父项右侧，越界则翻转到左侧/上移
async function openSubMenu(item, e) {
  if (!item.children?.length) {
    openSub.value = null
    subItems.value = []
    return
  }
  if (openSub.value === item.key) return
  openSub.value = item.key
  subItems.value = item.children
  const rect = e.currentTarget.getBoundingClientRect()
  subPos.value = { left: rect.right + 2, top: rect.top - 5 }
  await nextTick()
  const sub = subRoot.value
  if (!sub) return
  const r = sub.getBoundingClientRect()
  let { left, top } = subPos.value
  if (left + r.width > window.innerWidth - 8) left = Math.max(8, rect.left - r.width - 2)
  if (top + r.height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - r.height - 8)
  subPos.value = { left, top }
}

function onItemClick(item, e) {
  if (item.children?.length) {
    // 触屏/触摸板没有悬停，点击同样展开子菜单
    openSubMenu(item, e)
    return
  }
  emit('select', item)
  close()
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      ref="root"
      class="ctx-menu"
      :style="{ left: pos.left + 'px', top: pos.top + 'px', visibility: ready ? 'visible' : 'hidden' }"
      role="menu"
      @contextmenu.prevent
    >
      <template v-for="(item, i) in items" :key="item.key || `sep-${i}`">
        <div v-if="item.separator" class="ctx-sep" role="separator"></div>
        <button
          v-else
          type="button"
          role="menuitem"
          class="ctx-item"
          :class="{ danger: item.danger, subbed: openSub === item.key }"
          @mouseenter="openSubMenu(item, $event)"
          @click="onItemClick(item, $event)"
        >
          <ArtIcon v-if="item.icon" :name="item.icon" :tone="item.danger ? 'coral' : 'pearl'" :size="15" />
          <span class="ctx-label">{{ item.label }}</span>
          <ArtIcon v-if="item.active" name="check" tone="mint" :size="14" class="ctx-mark" />
          <ArtIcon
            v-else-if="item.children?.length"
            name="chevron-right"
            tone="pearl"
            :size="13"
            class="ctx-mark"
          />
        </button>
      </template>

      <div
        v-if="subItems.length"
        ref="subRoot"
        class="ctx-menu sub"
        :style="{ left: subPos.left + 'px', top: subPos.top + 'px' }"
        role="menu"
      >
        <button
          v-for="child in subItems"
          :key="child.key"
          type="button"
          role="menuitem"
          class="ctx-item"
          :class="{ danger: child.danger }"
          @click="onItemClick(child, $event)"
        >
          <ArtIcon v-if="child.icon" :name="child.icon" :tone="child.danger ? 'coral' : 'pearl'" :size="15" />
          <span class="ctx-label">{{ child.label }}</span>
          <ArtIcon v-if="child.active" name="check" tone="mint" :size="14" class="ctx-mark" />
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ctx-menu {
  position: fixed;
  z-index: 320;
  min-width: 168px;
  padding: 6px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.ctx-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 8px 10px;
  border-radius: var(--radius-xs);
  background: transparent;
  border: 1px solid transparent;
  box-shadow: none;
  text-align: left;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}
.ctx-item:hover,
.ctx-item.subbed {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 22%, var(--border));
  transform: none;
  box-shadow: none;
}
.ctx-item.danger {
  color: var(--danger);
}
.ctx-item.danger:hover {
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  border-color: color-mix(in srgb, var(--danger) 22%, transparent);
}

.ctx-label {
  flex: 1;
  min-width: 0;
}
.ctx-mark {
  flex-shrink: 0;
  margin-left: 12px;
}

.ctx-sep {
  height: 1px;
  margin: 5px 8px;
  background: var(--border);
}
</style>
