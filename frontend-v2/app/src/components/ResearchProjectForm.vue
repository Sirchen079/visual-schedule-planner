<script setup lang="ts">
import { ref } from 'vue'
import type { ProjectSpec } from '../api/research'
const props = defineProps<{ initial?: ProjectSpec; busy: boolean }>()
const emit = defineEmits<{ save: [spec: ProjectSpec]; cancel: [] }>()
const today = new Date()
const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
const form = ref<ProjectSpec>(props.initial ? JSON.parse(JSON.stringify(props.initial)) : {
  title: '', objective: '', background: '', kind: 'study', start_date: localDate, end_date: null,
  daily_minutes: 60, session_minutes: 45, weekdays: [0,1,2,3,4,5,6], window_start: null, window_end: null,
})
function save() { emit('save', { ...form.value, end_date: form.value.end_date || null, window_start: form.value.window_start || null, window_end: form.value.window_end || null }) }
</script>
<template>
  <form class="project-form" @submit.prevent="save">
    <h2>{{ initial ? '调整项目目标与时间' : '开始一个学习项目' }}</h2>
    <label>项目主题<input v-model="form.title" required maxlength="200" placeholder="例如：用 Python 分析自己的阅读记录"></label>
    <label>希望掌握什么，或完成什么产出<textarea v-model="form.objective" required maxlength="4000" rows="3"></textarea></label>
    <label>已有基础与其他约束<textarea v-model="form.background" maxlength="4000" rows="2" placeholder="例如：没有编程基础，每周末可以多投入一点时间"></textarea></label>
    <div class="pair"><label>项目类型<select v-model="form.kind"><option value="study">学习</option><option value="research">研究</option></select></label><label>开始日期<input v-model="form.start_date" type="date" required></label></div>
    <label>截止日期（可留空）<input v-model="form.end_date" type="date" :min="form.start_date"></label>
    <p class="hint">未填截止日期时，先规划从开始日起的两周。</p>
    <div class="pair"><label>每日最多投入（分钟）<input v-model.number="form.daily_minutes" type="number" min="15" max="480" required></label><label>单次最长（分钟）<input v-model.number="form.session_minutes" type="number" min="15" max="120" required></label></div>
    <fieldset><legend>可以安排的星期</legend><label v-for="(day,i) in ['一','二','三','四','五','六','日']" :key="day" class="check"><input v-model="form.weekdays" type="checkbox" :value="i">周{{ day }}</label></fieldset>
    <div class="pair"><label>每天可用时间，从<input v-model="form.window_start" type="time" :required="!!form.window_end"></label><label>到<input v-model="form.window_end" type="time" :required="!!form.window_start"></label></div>
    <p class="hint">时间留空时采用设置中的工作时段。规划会避开已有日程，并受每日任务容量限制。修改约束后可预览重排。</p>
    <div class="actions"><button type="button" @click="emit('cancel')" :disabled="busy">取消</button><button class="primary" :disabled="busy || !form.weekdays?.length">{{ busy ? '保存中…' : '保存项目' }}</button></div>
  </form>
</template>
