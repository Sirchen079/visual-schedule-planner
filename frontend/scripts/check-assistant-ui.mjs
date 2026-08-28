import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

// 助手 UI 已拆分为壳(AssistantView.vue)+ assistant/ 子组件,
// 断言按字面量实际所在文件分别检查。
function read(rel) {
  const p = resolve(__dirname, rel)
  return existsSync(p) ? readFileSync(p, 'utf8') : ''
}

const source = read('../src/views/AssistantView.vue')
const messageSource = read('../src/views/assistant/AssistantMessage.vue')
const chatSource = read('../src/views/assistant/AssistantChat.vue')
const aiApiSource = read('../src/api/ai.js')
const themeSource = read('../src/styles/theme.css')

const checks = [
  {
    name: 'compact assistant keeps settings control visible',
    pass: source.includes('mode-switch') && source.includes("@click=\"assistantMode = 'settings'\""),
  },
  {
    name: 'message bubbles contain long assistant replies',
    pass:
      !/\.message\s*\{[^}]*overflow:\s*visible/s.test(source) &&
      /\.message\s*\{[^}]*contain:\s*layout\s+paint/s.test(source) &&
      /\.assistant-shell:not\(\.fullscreen\)\s+\.message\.assistant,\s*\.assistant-shell:not\(\.fullscreen\)\s+\.message\.system\s*\{[^}]*width:\s*min\(92%,\s*430px\)/s.test(source),
  },
  {
    name: 'message bubbles opt out of flex shrinking',
    pass: /\.message\s*\{[^}]*flex:\s*0\s+0\s+auto/s.test(source),
  },
  {
    name: 'message list uses an always visible vertical scrollbar',
    pass: /\.messages\s*\{[^}]*overflow-y:\s*scroll/s.test(source),
  },
  {
    name: 'narrow viewports do not force non-fullscreen assistant to viewport height',
    pass: !/@media\s*\(max-width:\s*980px\)[\s\S]*?\.assistant-shell\s*\{[\s\S]*?height:\s*calc\(100vh - 24px\)/.test(source),
  },
  {
    name: 'floating assistant does not block the underlying page',
    pass: /\.assistant-layer\s*\{[^}]*pointer-events:\s*none/s.test(source) && /\.assistant-shell\s*\{[^}]*pointer-events:\s*auto/s.test(source),
  },
  {
    name: 'assistant replies use Vue structured blocks instead of v-html',
    pass:
      source.includes('parseMessageBlocks') &&
      source.includes('createMessage') &&
      messageSource.includes("block.type === 'list'") &&
      messageSource.includes("block.type === 'paragraph'") &&
      messageSource.includes('message.blocks') &&
      !source.includes('v-html=') &&
      !messageSource.includes('v-html='),
  },
  {
    name: 'floating assistant is non-modal and traps focus only in fullscreen',
    pass:
      source.includes(':role="fullscreen ? \'dialog\' : \'region\'"') &&
      source.includes(':aria-modal="fullscreen ? \'true\' : null"') &&
      source.includes('if (!open.value || !fullscreen.value) return'),
  },
  {
    name: 'mobile users keep a fullscreen-capable assistant',
    pass:
      source.includes("window.matchMedia?.('(max-width: 640px)')?.matches") &&
      !/\.assistant-shell:not\(\.fullscreen\)\s+\.fullscreen-action\s*\{[^}]*display:\s*none/s.test(source),
  },
  {
    name: 'failed chat send restores the user input',
    pass:
      source.includes('messages.value.splice(messageIndex, 1)') &&
      source.includes('restoreToInput') &&
      source.includes('if (restoreToInput && !input.value.trim()) input.value = text'),
  },
  {
    name: 'dangerous action cards render server-generated previews',
    pass:
      messageSource.includes('action.preview?.length') &&
      (source.includes('pending-preview') || messageSource.includes('pending-preview')) &&
      messageSource.includes('v-for="(line, previewIndex) in action.preview"'),
  },
  {
    name: 'AI API client sanitizes errors and applies timeouts',
    pass:
      aiApiSource.includes('redactErrorText') &&
      aiApiSource.includes('DEFAULT_TIMEOUT_MS') &&
      aiApiSource.includes('AbortController') &&
      !aiApiSource.includes('throw new Error(`请求失败 (${res.status}) ${text}`)'),
  },
  {
    name: 'global theme respects reduced-motion preferences',
    pass: themeSource.includes('@media (prefers-reduced-motion: reduce)'),
  },
]

const failures = checks.filter((check) => !check.pass)

if (failures.length) {
  console.error('Assistant UI regression check failed:')
  for (const failure of failures) console.error(`- ${failure.name}`)
  process.exit(1)
}

console.log(`Assistant UI regression check passed (${checks.length} checks)`)
