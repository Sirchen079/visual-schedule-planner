<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UserAnswer, UserInputRequest, UserQuestion } from '../../api/userInput'
import { useRunStore } from '../../stores/run'
import { useConversationStore } from '../../stores/conversation'

const props = defineProps<{ request: UserInputRequest; readonly?: boolean }>()
const run = useRunStore()
const conv = useConversationStore()
const answers = ref<Record<string, UserAnswer>>({})
watch(() => props.request.id, () => {
  const saved = conv.questionDrafts[String(props.request.id)] ?? {}
  answers.value = Object.fromEntries(props.request.questions.map(q => [q.id,
    JSON.parse(JSON.stringify(saved[q.id] ?? { selected: [], text: '' }))]))
}, { immediate: true })
watch(() => props.request.status, status => {
  if (status !== 'pending' && !props.readonly) conv.saveQuestionDraft(props.request.id, null)
}, { immediate: true })
const editable = computed(() => !props.readonly && props.request.status === 'pending')
const busy = computed(() => !!props.request.busy || run.hasLiveStream())
const complete = computed(() => props.request.questions.every(q => {
  const answer = answers.value[q.id]
  return answer && (answer.selected.length > 0 || answer.text.trim().length > 0)
}))
function persist() { conv.saveQuestionDraft(props.request.id, answers.value) }
function choose(question: UserQuestion, label: string) {
  const answer = answers.value[question.id]
  if (question.multi_select) answer.selected = answer.selected.includes(label)
    ? answer.selected.filter(value => value !== label) : [...answer.selected, label]
  else answer.selected = [label]
  persist()
}
function response(id: string) {
  const answer = props.request.answer.answers?.find(a => a.id === id)
  return answer ? [...answer.selected, answer.text].filter(Boolean).join('；') : '未提供答案'
}
const stateLabel = computed(() => ({ pending: '需要你的回答', answered: '已回答', skipped: '已跳过', expired: '已结束' })[props.request.status])
</script>

<template>
  <section class="question-card" :aria-label="stateLabel">
    <div class="question-head"><strong>{{ stateLabel }}</strong><span>信息与选择</span></div>
    <form v-if="editable" @submit.prevent="run.answerQuestion(request.id, answers)">
      <fieldset v-for="question in request.questions" :key="question.id" :disabled="busy">
        <legend>{{ question.question }}</legend>
        <span v-if="question.multi_select && question.options.length" class="hint">可选择多项</span>
        <label v-for="option in question.options" :key="option.label" class="option" :class="{ selected: answers[question.id]?.selected.includes(option.label) }">
          <input :type="question.multi_select ? 'checkbox' : 'radio'" :name="`question-${request.id}-${question.id}`"
            :checked="answers[question.id]?.selected.includes(option.label)" @change="choose(question, option.label)">
          <span><strong>{{ option.label }}</strong><small v-if="option.description">{{ option.description }}</small></span>
        </label>
        <label class="free-answer">{{ question.options.length ? '补充说明，或直接输入你的答案' : '你的回答' }}
          <textarea v-model="answers[question.id].text" rows="2" maxlength="4000" @input="persist" />
        </label>
      </fieldset>
      <footer><button type="button" :disabled="busy" @click="run.answerQuestion(request.id, {}, true)">跳过这组问题</button>
        <button class="submit" :disabled="busy || !complete">{{ request.busy ? '保存中…' : '提交并继续' }}</button></footer>
      <p class="hint">可以选择选项，也可以自由回答。提交后继续原任务。</p>
    </form>
    <div v-else class="answers">
      <div v-for="question in request.questions" :key="question.id"><strong>{{ question.question }}</strong><p>{{ response(question.id) }}</p></div>
    </div>
  </section>
</template>

<style scoped>
.question-card { border: 1px solid var(--amber-border); background: var(--bg-sink); border-radius: 10px; overflow: hidden; font-size: 13px; }
.question-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; padding: 12px; border-bottom: 1px solid var(--line); }
.question-head strong { color: var(--amber-soft); }
.question-head span, .hint { color: var(--ink-3); font-size: 11px; }
form, .answers { padding: 12px; }
fieldset { min-width: 0; border: 0; padding: 0; margin: 0 0 16px; }
legend { width: 100%; font-weight: 600; margin-bottom: 8px; line-height: 1.6; overflow-wrap: anywhere; }
.option { display: flex; align-items: flex-start; gap: 8px; padding: 9px; border: 1px solid var(--line); border-radius: 7px; margin: 6px 0; cursor: pointer; }
.option.selected { border-color: var(--amber-border); background: var(--bg-bubble); }
.option input { flex: none; margin-top: 3px; accent-color: var(--amber); }
.option strong { font-weight: 500; overflow-wrap: anywhere; }
.option small { display: block; margin-top: 3px; color: var(--ink-3); line-height: 1.5; overflow-wrap: anywhere; }
.free-answer { display: block; margin-top: 10px; color: var(--ink-2); font-size: 12px; }
textarea { display: block; width: 100%; box-sizing: border-box; resize: vertical; margin-top: 5px; padding: 8px; font: inherit; color: var(--ink); background: var(--bg-app); border: 1px solid var(--line); border-radius: 7px; }
textarea:focus-visible, button:focus-visible, input:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
footer { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
button { padding: 7px 10px; border: 1px solid var(--line); border-radius: 7px; color: var(--ink-2); background: var(--bg-app); cursor: pointer; font: inherit; }
button.submit { color: var(--amber-soft); border-color: var(--amber-border); }
button:disabled { opacity: .5; cursor: default; }
p.hint { margin: 8px 0 0; }
.answers > div + div { margin-top: 12px; }
.answers strong { font-weight: 500; }
.answers p { color: var(--ink-2); margin: 4px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
