import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const srcDir = resolve(__dirname, '../src')

function read(path) {
  return readFileSync(resolve(srcDir, path), 'utf8')
}

function readOptional(path) {
  const fullPath = resolve(srcDir, path)
  return existsSync(fullPath) ? readFileSync(fullPath, 'utf8') : ''
}

const files = {
  theme: read('styles/theme.css'),
  app: read('App.vue'),
  board: read('views/BoardView.vue'),
  overview: read('views/OverviewView.vue'),
  calendar: read('views/CalendarView.vue'),
  timeline: read('views/TimelineView.vue'),
  library: read('views/LibraryView.vue'),
  trash: read('views/TrashView.vue'),
  modal: read('components/TaskModal.vue'),
  reminders: read('components/RemindersPanel.vue'),
  taskCard: read('components/TaskCard.vue'),
  assistant: read('views/AssistantView.vue'),
  artIcon: readOptional('components/ArtIcon.vue'),
}

const allSource = Object.values(files).join('\n')

const requiredArtIconFiles = [
  'app',
  'board',
  'overview',
  'calendar',
  'timeline',
  'library',
  'trash',
  'modal',
  'reminders',
  'taskCard',
  'assistant',
]

const bannedTextIconMarkup = [
  /class="brand-icon"[^>]*>\s*[^<{][^<]{0,8}\s*</,
  /class="page-title-icon"[^>]*>\s*[^<{][^<]{0,8}\s*</,
  /class="ctl-ico"[^>]*>\s*[^<{][^<]{0,8}\s*</,
  /class="btn-icon"[^>]*>\s*[^<{][^<]{0,8}\s*</,
  /class="section-icon"[^>]*>\s*[^<{][^<]{0,8}\s*</,
  /class="row-icon"[^>]*>\s*[^<{][^<]{0,8}\s*</,
  /class="file-icon"[^>]*>\s*\{\{/,
  /class="assistant-fab"(?:(?!<\/button>)[\s\S])*?<span>\s*[^<{][^<]{0,8}\s*<\/span>/,
]

const requiredIconNames = [
  'brand',
  'board',
  'overview',
  'calendar',
  'timeline',
  'library',
  'trash',
  'assistant',
  'plus',
  'search',
  'priority',
  'tag',
  'sort',
  'bell',
  'moon',
  'sun',
  'close',
  'restore',
  'upload',
  'file',
  'image',
  'link',
  'archive',
  'task',
  'steps',
]

const bannedRoughCopy = [
  '把任务轻轻放进海里',
  '贝壳已经拾上岸',
  '漂浮的杂物',
]

const bannedDecorativeGlyphs = [
  '🔍',
  '🎯',
  '🏷',
  '↕️',
  '🗂️',
  '📎',
  '🌊',
  '🐚',
  '✨',
  '☁️',
  '🏖️',
  '🔔',
  '✧',
  '✦',
  '▶️',
  '🔗',
  '🖼️',
  '📄',
  '🗜️',
  '✅',
  '🗑️',
  '⚠️',
  '⏰',
]

const checks = [
  {
    name: 'global theme no longer renders animated decorative ocean layers',
    pass:
      !/ocean-breathe|wave-sway|bubble-rise|gentle-float/.test(files.theme),
  },
  {
    name: 'decorative float utility is removed from production UI',
    pass:
      !/class="[^"]*\bfloat(?:-slow|-delay)?\b/.test(allSource) &&
      !/\.float(?:-slow|-delay)?\b/.test(files.theme),
  },
  {
    name: 'theme uses restrained application radii',
    pass:
      /--radius:\s*16px/.test(files.theme) &&
      /--radius-lg:\s*20px/.test(files.theme) &&
      /--radius-sm:\s*12px/.test(files.theme),
  },
  {
    name: 'buttons no longer use shimmer pseudo-element',
    pass: !/button::after/.test(files.theme) && !/translateX\(-120%\)/.test(files.theme),
  },
  {
    name: 'rough healing copy removed from major views',
    pass: bannedRoughCopy.every((word) => !allSource.includes(word)),
  },
  {
    name: 'major UI avoids decorative emoji glyphs',
    pass: bannedDecorativeGlyphs.every((glyph) => !allSource.includes(glyph)),
  },
  {
    name: 'task cards keep subtask detail stable instead of hover expanding',
    pass: !/\.task-card:hover\s+\.sub-list/.test(files.taskCard) && !/max-height:\s*340px/.test(files.taskCard),
  },
  {
    name: 'AI assistant keeps reachable mode tabs',
    pass:
      files.assistant.includes('role="tab"') &&
      files.assistant.includes("assistantMode = 'chat'") &&
      (files.assistant.includes("assistantMode = 'history'") ||
        files.assistant.includes("assistantMode.value = 'history'") ||
        files.assistant.includes('@click="showHistory"')) &&
      files.assistant.includes("assistantMode = 'settings'"),
  },
  {
    name: 'custom art icon component exists and exposes the full app icon set',
    pass:
      files.artIcon.includes('defineProps') &&
      requiredIconNames.every((name) => files.artIcon.includes(`'${name}'`)),
  },
  {
    name: 'major UI surfaces import and render ArtIcon',
    pass: requiredArtIconFiles.every((key) => files[key].includes('ArtIcon')),
  },
  {
    name: 'text-only icon badge markup is removed from major UI',
    pass: bannedTextIconMarkup.every((pattern) => !pattern.test(allSource)),
  },
  {
    name: 'primary action icons have an on-accent contrast tone',
    pass:
      files.artIcon.includes('.tone-on-accent') &&
      !/class="(?:create-btn|upload-btn|send-action)"[\s\S]{0,180}<ArtIcon[^>]+tone="pearl"/.test(allSource),
  },
  {
    name: 'art icon sizes follow the visual hierarchy',
    pass:
      /\.art-icon svg\s*\{[\s\S]{0,120}width:\s*78%[\s\S]{0,80}height:\s*78%/.test(files.artIcon) &&
      /<ArtIcon name="brand"[\s\S]{0,120}:size="38"[\s\S]{0,80}tile/.test(files.app) &&
      /<ArtIcon :name="tab.icon"[\s\S]{0,140}:size="20"/.test(files.app) &&
      /\.tab :deep\(\.art-icon\)\s*\{[\s\S]{0,80}width:\s*22px[\s\S]{0,80}height:\s*22px/.test(files.app) &&
      [
        [files.board, 'board'],
        [files.overview, 'overview'],
        [files.calendar, 'calendar'],
        [files.timeline, 'timeline'],
        [files.library, 'library'],
        [files.trash, 'trash'],
        [files.assistant, 'assistant'],
      ].every(([source, icon]) => new RegExp(`<ArtIcon name="${icon}"[\\s\\S]{0,120}:size="36"`).test(source)) &&
      /class="create-btn"[\s\S]{0,180}<ArtIcon name="plus"[\s\S]{0,80}:size="20"/.test(files.board) &&
      /class="create-btn"[\s\S]{0,180}<ArtIcon name="plus"[\s\S]{0,80}:size="20"/.test(files.calendar) &&
      /class="create-btn"[\s\S]{0,180}<ArtIcon name="plus"[\s\S]{0,80}:size="20"/.test(files.timeline) &&
      /class="upload-btn"[\s\S]{0,180}<ArtIcon name="upload"[\s\S]{0,80}:size="20"/.test(files.library) &&
      /class="send-action"[\s\S]{0,280}<ArtIcon name="send"[\s\S]{0,80}:size="20"/.test(files.assistant) &&
      /class="file-art"[\s\S]{0,260}:size="84"/.test(files.library) &&
      /class="row-art"[\s\S]{0,120}:size="42"/.test(files.trash) &&
      /class="file-art compact"[\s\S]{0,280}:size="40"/.test(files.modal),
  },
  {
    name: 'mobile top navigation avoids clipped tab labels',
    pass:
      files.app.includes('@media (max-width: 720px)') &&
      files.app.includes('class="tab-label"') &&
      !/\.tab\s+span\s*\{[\s\S]*display:\s*none/.test(files.app) &&
      /\.tab-label\s*\{[\s\S]*display:\s*none/.test(files.app) &&
      /\.tab\s*\{[\s\S]*width:\s*38px/.test(files.app),
  },
  {
    name: 'reduced motion preference remains globally respected',
    pass: files.theme.includes('@media (prefers-reduced-motion: reduce)'),
  },
]

const failures = checks.filter((check) => !check.pass)

if (failures.length) {
  console.error('Frontend polish regression check failed:')
  for (const failure of failures) console.error(`- ${failure.name}`)
  process.exit(1)
}

console.log(`Frontend polish regression check passed (${checks.length} checks)`)
