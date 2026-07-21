<script setup>
// 首次启动欢迎引导：4 屏轮播（定位 / 核心视图 / 快捷键 / AI 助手）。
// 「跳过」与「开始使用」都会写入 onboarding_done=1，只出现一次。
// 触发条件（App.vue）：onboarding_done !== '1' 且任务列表为空，避免打扰老用户。
import { computed, ref } from 'vue'
import ArtIcon from './ArtIcon.vue'
import BaseModal from './ui/BaseModal.vue'
import { updateSettings } from '../api/settings'
import heroUrl from '../assets/hero.png'

defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['done'])

const step = ref(0)
const SCREEN_COUNT = 4
const isLast = computed(() => step.value === SCREEN_COUNT - 1)

const pillars = [
  { icon: 'board', tone: 'aqua', title: '看板管任务', desc: '三列拖拽流转，自然语言快速创建' },
  { icon: 'calendar', tone: 'mint', title: '日历看安排', desc: '双击格子按日期创建，拖拽直接改期' },
  { icon: 'overview', tone: 'sand', title: '总览看进展', desc: '完成情况与节奏一眼看清' },
]

const shortcuts = [
  { keys: ['Ctrl', 'K'], desc: '命令面板：一句话找到所有功能' },
  { keys: ['?'], desc: '快捷键帮助：随时查看当前可用按键' },
  { keys: ['Ctrl', 'Shift', 'A'], desc: '全局快速捕获（桌面端）：任何界面都能记录灵感' },
]

function prev() {
  if (step.value > 0) step.value -= 1
}
function next() {
  if (!isLast.value) step.value += 1
}

// 完成或跳过统一收口：写入标记位后关闭；写入失败也先关闭，不阻断使用
async function finish() {
  try {
    await updateSettings({ onboarding_done: '1' })
  } catch {
    // 标记写入失败时下次启动会再次显示引导，属可接受降级
  }
  step.value = 0
  emit('done')
}
</script>

<template>
  <BaseModal
    :open="open"
    size="md"
    :closable="false"
    :close-on-overlay="false"
    label="欢迎使用知时"
    @close="finish"
  >
    <div class="welcome">
      <!-- 第 1 屏：欢迎 + 定位 -->
      <div v-if="step === 0" class="screen screen-hero">
        <img class="hero-img" :src="heroUrl" alt="知时欢迎插画" />
        <h2 class="screen-title">欢迎使用知时</h2>
        <p class="screen-desc">本地优先的日程、任务与资料管理。数据都在你自己的电脑上，安心又顺手。</p>
      </div>

      <!-- 第 2 屏：核心三板斧 -->
      <div v-else-if="step === 1" class="screen">
        <h2 class="screen-title">核心三板斧</h2>
        <p class="screen-desc">三个视图覆盖日常安排的主线，数字键 1–9 可快速切换。</p>
        <div class="pillar-list">
          <div v-for="p in pillars" :key="p.title" class="pillar-row">
            <ArtIcon :name="p.icon" :tone="p.tone" :size="30" tile :label="p.title" />
            <div class="pillar-copy">
              <strong>{{ p.title }}</strong>
              <span class="muted">{{ p.desc }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 第 3 屏：效率秘籍 -->
      <div v-else-if="step === 2" class="screen">
        <h2 class="screen-title">效率秘籍</h2>
        <p class="screen-desc">记住这三个按键，日常操作可以快很多。</p>
        <div class="shortcut-list">
          <div v-for="s in shortcuts" :key="s.desc" class="shortcut-row">
            <span class="shortcut-keys">
              <kbd v-for="k in s.keys" :key="k">{{ k }}</kbd>
            </span>
            <span class="shortcut-desc">{{ s.desc }}</span>
          </div>
        </div>
      </div>

      <!-- 第 4 屏：AI 助手 -->
      <div v-else class="screen">
        <div class="ai-icon-wrap">
          <ArtIcon name="assistant" tone="aqua" :size="40" tile label="知时助手" />
        </div>
        <h2 class="screen-title">还有一位 AI 助手</h2>
        <p class="screen-desc">
          知时助手可以帮你拆解任务、安排日程、生成日报周报。这是可选功能：
          需要时在助手面板的「配置」里接入自己的模型接口即可使用，不配置也不影响其他所有功能。
        </p>
      </div>

      <!-- 底部：进度点 + 操作按钮 -->
      <div class="welcome-foot">
        <button class="ghost skip-btn" type="button" @click="finish">跳过</button>
        <div class="dots" aria-hidden="true">
          <span
            v-for="i in SCREEN_COUNT"
            :key="i"
            class="dot"
            :class="{ active: step === i - 1 }"
          ></span>
        </div>
        <div class="foot-actions">
          <button v-if="step > 0" class="ghost" type="button" @click="prev">上一步</button>
          <button v-if="!isLast" type="button" class="next-btn" data-autofocus @click="next">下一步</button>
          <button v-else type="button" class="next-btn" data-autofocus @click="finish">开始使用</button>
        </div>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.welcome {
  display: flex;
  flex-direction: column;
  padding: 26px 26px 20px;
  min-height: 420px;
}

.screen {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  animation: screen-in 0.25s ease both;
}

@keyframes screen-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.screen-title {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: var(--text);
}

.screen-desc {
  margin: 10px auto 0;
  max-width: 44ch;
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text-soft);
}

.hero-img {
  width: min(280px, 70%);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  margin-bottom: 18px;
}

.pillar-list {
  display: grid;
  gap: 10px;
  margin-top: 20px;
  width: 100%;
  max-width: 400px;
}

.pillar-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
  text-align: left;
}

.pillar-copy {
  display: grid;
  gap: 3px;
}

.pillar-copy strong {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text);
}

.shortcut-list {
  display: grid;
  gap: 10px;
  margin-top: 20px;
  width: 100%;
  max-width: 440px;
}

.shortcut-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 14px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
  text-align: left;
}

.shortcut-keys {
  flex-shrink: 0;
  display: inline-flex;
  gap: 4px;
}

.shortcut-keys kbd {
  padding: 4px 9px;
  border-radius: 6px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom-width: 2px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
}

.shortcut-desc {
  font-size: 13px;
  color: var(--text-soft);
}

.ai-icon-wrap {
  margin-bottom: 14px;
}

.welcome-foot {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
  margin-top: 22px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.skip-btn {
  padding: 8px 16px;
}

.dots {
  display: flex;
  justify-content: center;
  gap: 7px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--surface-3);
  border: 1px solid var(--border);
  transition: background 0.2s ease, transform 0.2s ease;
}

.dot.active {
  background: var(--accent);
  border-color: var(--accent);
  transform: scale(1.25);
}

.foot-actions {
  display: flex;
  gap: 10px;
}

.next-btn {
  padding: 9px 22px;
  font-weight: 700;
}

@media (max-width: 560px) {
  .welcome {
    padding: 20px 16px 14px;
    min-height: 0;
  }
  .welcome-foot {
    grid-template-columns: 1fr;
    justify-items: center;
  }
  .foot-actions {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
