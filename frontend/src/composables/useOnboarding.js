// 新手引导状态（模块级单例，全应用共享响应式）。
// 默认 true：设置未加载完成前不闪出任何新手元素，避免老用户升级时被晃一下。
import { ref } from 'vue'
import { getSettings, updateSettings } from '../api/settings'

const onboardingDone = ref(true)
const loaded = ref(false)

// 从已拉取的设置对象同步状态——供 App.vue 复用同一次 getSettings 调用，避免重复请求
function hydrate(s) {
  if (s) onboardingDone.value = s.onboarding_done === '1'
  loaded.value = true
}

// 独立拉取一次设置并同步状态（未复用 App.vue 调用链的组件可用）
async function load() {
  try {
    const s = await getSettings()
    onboardingDone.value = s.onboarding_done === '1'
  } catch {
    // 设置拉取失败保持默认 true，不打扰
  }
  loaded.value = true
}

// 完成引导：写入标记位，共享状态立即翻转为 true，看板空态 overlay 即时消失
async function markDone() {
  await updateSettings({ onboarding_done: '1' })
  onboardingDone.value = true
}

// 重置引导：标记位翻回 false，空看板 overlay 立即恢复，下次启动欢迎页再次弹出
async function reset() {
  await updateSettings({ onboarding_done: '0' })
  onboardingDone.value = false
}

export function useOnboarding() {
  return { onboardingDone, loaded, hydrate, load, markDone, reset }
}
