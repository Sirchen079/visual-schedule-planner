<script setup>
// 首次启动欢迎引导：4 屏轮播（定位 / 板块功能 / 基本操作 / AI 配置）。
// 「跳过」与「开始使用」都会写入 onboarding_done=1，只出现一次。
// 触发条件（App.vue）：onboarding_done !== '1' 且任务列表为空，避免打扰老用户。
// 完成写入走 useOnboarding 共享单例，完成后看板空态 overlay 即时消失，无需刷新。
import { computed, ref } from 'vue'
import ArtIcon from './ArtIcon.vue'
import BaseModal from './ui/BaseModal.vue'
import heroUrl from '../assets/hero.png'
import { useOnboarding } from '../composables/useOnboarding'

defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['done'])

const { markDone } = useOnboarding()

const step = ref(0)
const SCREEN_COUNT = 4
const isLast = computed(() => step.value === SCREEN_COUNT - 1)

// 第 2 屏：各板块职责（图标名对齐 ArtIcon 已注册名，文案对齐真实导航）
const modules = [
  { icon: 'board', tone: 'aqua', title: '看板', desc: '按「待办 / 进行中 / 完成」三列组织全部任务，状态一目了然' },
  { icon: 'overview', tone: 'sand', title: '总览', desc: '汇总当日任务、习惯与日程，作为每日起始视图' },
  { icon: 'calendar', tone: 'mint', title: '日历', desc: '以月视图查看任务的日期与时间安排' },
  { icon: 'timeline', tone: 'aqua', title: '时间轴', desc: '以单日时间线呈现任务与日程' },
  { icon: 'flag', tone: 'sand', title: '习惯 / 日记 / 目标', desc: '长期记录与跟踪工具，可在设置中关闭入口' },
  { icon: 'assistant', tone: 'mint', title: '知时助手', desc: '右下角常驻的 AI 助手，配置方式见下一页' },
]

// 第 3 屏：基本操作（鼠标 / GUI 操作，全程不含任何快捷键教学）
const ops = [
  { icon: 'plus', tone: 'aqua', title: '创建任务', desc: '在看板顶部输入框输入内容，按回车创建。支持自然语言解析——例如输入「明天15点写周报 #工作 !高」，可自动识别时间、标签与优先级' },
  { icon: 'sort', tone: 'mint', title: '拖动卡片', desc: '在看板各列之间拖动任务卡片以变更状态' },
  { icon: 'file', tone: 'sand', title: '编辑任务', desc: '点击任务卡片可补充详情、添加子任务、上传附件及设置提醒' },
  { icon: 'restore', tone: 'aqua', title: '删除与恢复', desc: '删除的任务将移入回收站，可在回收站中恢复' },
]

// 第 4 屏：AI 模型配置步骤
const aiSteps = [
  '点击右下角的「知时助手」图标，打开助手面板',
  '切换到顶部「设置」页签',
  '接口格式选择 OpenAI Chat Completions（DeepSeek、通义千问、智谱、Kimi 等均兼容）',
  '填写 API Key、Base URL（如 DeepSeek 为 https://api.deepseek.com）与模型名称',
  '保存后返回对话页，发送任意消息验证连接',
]

function prev() {
  if (step.value > 0) step.value -= 1
}
function next() {
  if (!isLast.value) step.value += 1
}

// 纯展示用辅助：把步骤文本里的「书名号片段」高亮，无逻辑副作用
function formatStep(s) {
  return s.replace(/「([^」]+)」/g, '<b>「$1」</b>')
}

// 完成或跳过统一收口：写入标记位后关闭；写入失败也先关闭，不阻断使用
async function finish() {
  try {
    await markDone()
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
        <p class="screen-desc">集成任务、日程、习惯与 AI 助手的时间管理工具。数据存储在本地，不依赖云服务。</p>
      </div>

      <!-- 第 2 屏：板块介绍 -->
      <div v-else-if="step === 1" class="screen">
        <h2 class="screen-title">主要功能模块</h2>
        <p class="screen-desc">各模块独立运作，可在设置中关闭不需要的入口。</p>
        <div class="feature-list">
          <div v-for="m in modules" :key="m.title" class="feature-row">
            <ArtIcon :name="m.icon" :tone="m.tone" :size="26" tile :label="m.title" />
            <div class="feature-copy">
              <strong>{{ m.title }}</strong>
              <span class="muted">{{ m.desc }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 第 3 屏：基本操作 -->
      <div v-else-if="step === 2" class="screen">
        <h2 class="screen-title">基本操作</h2>
        <p class="screen-desc">通过鼠标即可完成主要操作。</p>
        <div class="feature-list">
          <div v-for="o in ops" :key="o.title" class="feature-row">
            <ArtIcon :name="o.icon" :tone="o.tone" :size="26" tile :label="o.title" />
            <div class="feature-copy">
              <strong>{{ o.title }}</strong>
              <span class="muted">{{ o.desc }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 第 4 屏：配置 AI 模型 -->
      <div v-else class="screen">
        <div class="ai-icon-wrap">
          <ArtIcon name="assistant" tone="aqua" :size="40" tile label="知时助手" />
        </div>
        <h2 class="screen-title">配置 AI 模型</h2>
        <p class="screen-desc">
          知时助手需要配置大模型 API Key 后方可使用。请求直接发送至所选服务商，不经过第三方中转。
        </p>
        <ol class="ai-steps">
          <li v-for="(s, i) in aiSteps" :key="i">
            <span class="step-num">{{ i + 1 }}</span>
            <span class="step-text" v-html="formatStep(s)"></span>
          </li>
        </ol>
        <p class="ai-tail muted">配置完成后，助手可协助创建任务、拆分子任务及生成报告。</p>
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

.feature-list {
  display: grid;
  gap: 8px;
  margin-top: 16px;
  width: 100%;
  max-width: 420px;
}

.feature-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
  text-align: left;
}

.feature-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.feature-copy strong {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}

.feature-copy .muted {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text-soft);
}

.ai-icon-wrap {
  margin-bottom: 14px;
}

.ai-steps {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
  width: 100%;
  max-width: 440px;
  text-align: left;
  display: grid;
  gap: 8px;
}

.ai-steps li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
}

.step-num {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.step-text {
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-soft);
}

.step-text :deep(b) {
  color: var(--text);
  font-weight: 700;
}

.ai-tail {
  margin: 12px 0 0;
  font-size: 12.5px;
  max-width: 44ch;
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
