<script>
// 读取当前主题的 CSS 变量（getComputedStyle 已按 data-theme 解析）
export function cssVar(name, fallback = '') {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}
</script>

<script setup>
// echarts 基础容器：按需注册所需图表/组件，挂载时 init，
// option 深度变化整体重设（notMerge），ResizeObserver 自适应，
// 监听 <html data-theme> 变化后重绘，让 option 里的 cssVar 取色跟随主题。
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, HeatmapChart, LineChart, PieChart } from 'echarts/charts'
import {
  CalendarComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  BarChart,
  HeatmapChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CalendarComponent,
  VisualMapComponent,
  CanvasRenderer,
])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '260px' },
})

const el = ref(null)
let chart = null
let resizeObserver = null
let themeObserver = null

function render() {
  if (!chart || !props.option) return
  chart.setOption(props.option, { notMerge: true })
}

onMounted(() => {
  chart = echarts.init(el.value, null, { renderer: 'canvas' })
  render()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(el.value)
  themeObserver = new MutationObserver(() => render())
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  })
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  themeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" class="base-chart" :style="{ height }"></div>
</template>

<style scoped>
.base-chart {
  width: 100%;
  min-width: 0;
}
</style>
