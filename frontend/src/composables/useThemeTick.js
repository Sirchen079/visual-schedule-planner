import { onBeforeUnmount, onMounted, ref } from 'vue'

// data-theme 变化计数：图表 option 的 computed 依赖它，
// 主题切换时重建 option，让 cssVar 取色随深浅色更新。
export function useThemeTick() {
  const tick = ref(0)
  let observer = null
  onMounted(() => {
    observer = new MutationObserver(() => {
      tick.value += 1
    })
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
  })
  onBeforeUnmount(() => observer?.disconnect())
  return tick
}
