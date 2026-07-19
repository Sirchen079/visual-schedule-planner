<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
  tone: { type: String, default: 'aqua' },
  tile: { type: Boolean, default: false },
  label: { type: String, default: '' },
  labelText: { type: String, default: '' },
})

const ICON_NAMES = [
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
  'check',
  'alert',
  'upload',
  'file',
  'image',
  'link',
  'archive',
  'task',
  'steps',
  'flag',
  'chevron-left',
  'chevron-right',
  'refresh',
  'expand',
  'send',
]

const aliases = {
  attachment: 'file',
  delete: 'trash',
  document: 'file',
  folder: 'library',
  reminder: 'bell',
}

const iconName = computed(() => {
  const resolved = aliases[props.name] || props.name
  return ICON_NAMES.includes(resolved) ? resolved : 'file'
})

const sizePx = computed(() =>
  typeof props.size === 'number' ? `${props.size}px` : props.size
)
const decorative = computed(() => !props.label)
const fileLabel = computed(() => props.labelText.slice(0, 5).toUpperCase())
</script>

<template>
  <span
    :class="['art-icon', `tone-${tone}`, { tile }]"
    :style="{ '--icon-size': sizePx }"
    :role="decorative ? null : 'img'"
    :aria-label="decorative ? null : label"
    :aria-hidden="decorative ? 'true' : null"
  >
    <svg viewBox="0 0 24 24" focusable="false">
      <circle v-if="tile" class="soft-orbit" cx="12" cy="12" r="9.2" />

      <g v-if="iconName === 'brand'">
        <path d="M12 2.8c-1 2-3.9 5.6-4.47 7.54a5.2 5.2 0 1 0 8.94 0C15.9 8.4 13 4.8 12 2.8Z" />
        <path d="M12 13l-2.17-1.25" />
        <path d="M12 13l2.86-1.65" />
        <circle class="pearl" cx="12" cy="13" r="0.8" />
      </g>
      <g v-else-if="iconName === 'board'">
        <rect x="4" y="5" width="4.5" height="13.5" rx="1.4" />
        <rect x="9.8" y="5" width="4.5" height="13.5" rx="1.4" />
        <rect x="15.5" y="5" width="4.5" height="13.5" rx="1.4" />
        <path d="M5.5 8h1.6M11.3 10h1.6M17 7.8h1.6" />
      </g>
      <g v-else-if="iconName === 'overview'">
        <path d="M4.5 15.8a8 8 0 1 1 15 0" />
        <path d="M12 15.6l3.8-5.2" />
        <path d="M7.4 15.8h9.2" />
        <circle class="pearl" cx="12" cy="15.8" r="1.5" />
      </g>
      <g v-else-if="iconName === 'calendar'">
        <rect x="4.2" y="5.2" width="15.6" height="14.2" rx="2" />
        <path d="M4.2 9.4h15.6M8 3.8v3M16 3.8v3" />
        <path d="M8 13h2M12 13h2M16 13h1M8 16.2h2M12 16.2h2" />
      </g>
      <g v-else-if="iconName === 'timeline'">
        <path d="M4.5 17.2h15" />
        <path d="M6 14.5V8.8M12 14.5V5.8M18 14.5v-4" />
        <circle class="pearl" cx="6" cy="8.8" r="1.6" />
        <circle class="pearl" cx="12" cy="5.8" r="1.6" />
        <circle class="pearl" cx="18" cy="10.5" r="1.6" />
      </g>
      <g v-else-if="iconName === 'library'">
        <path d="M4 7.4a2 2 0 0 1 2-2h4l1.6 2h6.4a2 2 0 0 1 2 2v7.2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" />
        <path d="M6.4 11.2h11.2M7.4 14.6h6.2" />
      </g>
      <g v-else-if="iconName === 'trash'">
        <path d="M7.2 8.2h9.6l-.7 10.2a1.8 1.8 0 0 1-1.8 1.6H9.7a1.8 1.8 0 0 1-1.8-1.6Z" />
        <path d="M5.6 8.2h12.8M9.5 6.1h5M10.2 11.4v5M13.8 11.4v5" />
      </g>
      <g v-else-if="iconName === 'assistant'">
        <path d="M12 4.2l1.6 4 4 1.6-4 1.6-1.6 4-1.6-4-4-1.6 4-1.6Z" />
        <circle class="pearl" cx="18" cy="17" r="1.8" />
        <path d="M5.2 17.8c2.5 1.8 5 1.8 7.4 0" />
      </g>
      <g v-else-if="iconName === 'plus'">
        <circle cx="12" cy="12" r="7.6" />
        <path d="M12 8.4v7.2M8.4 12h7.2" />
      </g>
      <g v-else-if="iconName === 'search'">
        <circle cx="10.6" cy="10.6" r="5.2" />
        <path d="M14.5 14.5l4.2 4.2" />
        <path d="M8.2 10.4h4.6" />
      </g>
      <g v-else-if="iconName === 'priority'">
        <circle cx="12" cy="12" r="7.4" />
        <circle class="pearl" cx="12" cy="12" r="3.2" />
        <path d="M12 4.6v2.1M19.4 12h-2.1M12 19.4v-2.1M4.6 12h2.1" />
      </g>
      <g v-else-if="iconName === 'tag'">
        <path d="M5.2 6.2h6.4l7.2 7.2a2 2 0 0 1 0 2.8l-2.6 2.6a2 2 0 0 1-2.8 0L6.2 11.6V5.2" />
        <circle class="pearl" cx="9" cy="9" r="1.3" />
      </g>
      <g v-else-if="iconName === 'sort'">
        <path d="M8 5.5v12.8M8 18.3l-2.4-2.4M8 18.3l2.4-2.4" />
        <path d="M16 18.5V5.7M16 5.7l-2.4 2.4M16 5.7l2.4 2.4" />
      </g>
      <g v-else-if="iconName === 'bell'">
        <path d="M6.5 16.5h11c-1.2-1.2-1.5-2.9-1.5-5 0-2.8-1.6-5-4-5s-4 2.2-4 5c0 2.1-.3 3.8-1.5 5Z" />
        <path d="M10.2 18.2c.4 1 1 1.5 1.8 1.5s1.4-.5 1.8-1.5M12 4.5V3.6" />
      </g>
      <g v-else-if="iconName === 'moon'">
        <path d="M17.8 15.4A7.1 7.1 0 0 1 8.6 6.2a7.1 7.1 0 1 0 9.2 9.2Z" />
        <path d="M15.8 6.2h2.4M17 5v2.4" />
      </g>
      <g v-else-if="iconName === 'sun'">
        <circle class="pearl" cx="12" cy="12" r="3.6" />
        <path d="M12 3.8v2M12 18.2v2M3.8 12h2M18.2 12h2M6.2 6.2l1.4 1.4M16.4 16.4l1.4 1.4M17.8 6.2l-1.4 1.4M7.6 16.4l-1.4 1.4" />
      </g>
      <g v-else-if="iconName === 'close'">
        <circle cx="12" cy="12" r="7.5" />
        <path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6" />
      </g>
      <g v-else-if="iconName === 'restore'">
        <path d="M7.2 8.6a6.4 6.4 0 1 1-1.1 5.5" />
        <path d="M7.2 8.6H4.4V5.8" />
        <path d="M12 9v4.2l2.8 1.6" />
      </g>
      <g v-else-if="iconName === 'check'">
        <circle cx="12" cy="12" r="8.4" />
        <path d="M8.2 12.4l2.6 2.6 5-5.4" />
      </g>
      <g v-else-if="iconName === 'alert'">
        <path d="M12 4.4 3.6 18.8h16.8L12 4.4Z" />
        <path d="M12 9.6v4.4" />
        <path d="M12 16.6v.2" />
      </g>
      <g v-else-if="iconName === 'upload'">
        <path d="M5 17.4v1.2a1.8 1.8 0 0 0 1.8 1.8h10.4a1.8 1.8 0 0 0 1.8-1.8v-1.2" />
        <path d="M12 15.8V4.6M8.5 8.1L12 4.6l3.5 3.5" />
      </g>
      <g v-else-if="iconName === 'task'">
        <rect x="5" y="4.8" width="14" height="15" rx="2" />
        <path d="M8.2 9.2l1.4 1.4 2.5-3M8.2 14.6h7.5" />
      </g>
      <g v-else-if="iconName === 'steps'">
        <path d="M6.4 6.8h4.8v4.8H6.4ZM12.8 12.4h4.8v4.8h-4.8Z" />
        <path d="M11.2 9.2h2.4a2 2 0 0 1 2 2v1.2" />
      </g>
      <g v-else-if="iconName === 'flag'">
        <path d="M6.4 20.2V4.4" />
        <path d="M6.4 5.2h10.4l-2.6 3.6 2.6 3.6H6.4" />
        <circle class="pearl" cx="6.4" cy="4.4" r="0.9" />
      </g>
      <g v-else-if="iconName === 'chevron-left'">
        <path d="M14.8 6.8L9.6 12l5.2 5.2" />
      </g>
      <g v-else-if="iconName === 'chevron-right'">
        <path d="M9.2 6.8l5.2 5.2-5.2 5.2" />
      </g>
      <g v-else-if="iconName === 'refresh'">
        <path d="M6.2 8.8a6.8 6.8 0 0 1 11-1.8l1.1 1.1" />
        <path d="M18.3 5.2v3h-3" />
        <path d="M17.8 15.2a6.8 6.8 0 0 1-11 1.8l-1.1-1.1" />
        <path d="M5.7 18.8v-3h3" />
      </g>
      <g v-else-if="iconName === 'expand'">
        <path d="M8.6 5.2H5.2v3.4M5.2 5.2l5 5" />
        <path d="M15.4 18.8h3.4v-3.4M18.8 18.8l-5-5" />
      </g>
      <g v-else-if="iconName === 'send'">
        <path d="M4.6 12 19 5.2l-4.2 13.6-3.1-5.3Z" />
        <path d="M11.7 13.5 19 5.2" />
      </g>
      <g v-else-if="iconName === 'image'">
        <rect x="4.6" y="5.4" width="14.8" height="13.2" rx="2" />
        <path d="M7.2 15.8l3.2-3.5 2.4 2.4 1.6-1.8 2.8 2.9" />
        <circle class="pearl" cx="15.8" cy="9" r="1.3" />
        <text v-if="fileLabel" x="12" y="21.5">{{ fileLabel }}</text>
      </g>
      <g v-else-if="iconName === 'link'">
        <path d="M9.8 14.2l-1.2 1.2a3 3 0 0 1-4.2-4.2l2.4-2.4a3 3 0 0 1 4.2 0" />
        <path d="M14.2 9.8l1.2-1.2a3 3 0 1 1 4.2 4.2l-2.4 2.4a3 3 0 0 1-4.2 0" />
        <path d="M9.4 14.6l5.2-5.2" />
        <text v-if="fileLabel" x="12" y="21.5">{{ fileLabel }}</text>
      </g>
      <g v-else-if="iconName === 'archive'">
        <path d="M5.2 8.2h13.6v9.6a1.8 1.8 0 0 1-1.8 1.8H7a1.8 1.8 0 0 1-1.8-1.8Z" />
        <path d="M4.5 5.2h15v3h-15ZM9.6 12h4.8" />
        <text v-if="fileLabel" x="12" y="21.5">{{ fileLabel }}</text>
      </g>
      <g v-else>
        <path d="M7 4.8h7.1L18 8.7v9.5a1.8 1.8 0 0 1-1.8 1.8H7.8A1.8 1.8 0 0 1 6 18.2V6.6a1.8 1.8 0 0 1 1-1.8Z" />
        <path d="M14 4.8v4h4M8.8 12.2h6.4M8.8 15.2h4.2" />
        <text v-if="fileLabel" x="12" y="21.5">{{ fileLabel }}</text>
      </g>
    </svg>
  </span>
</template>

<style scoped>
.art-icon {
  --icon-size: 20px;
  --icon-color: var(--accent);
  --icon-glow: var(--accent-glow);
  display: inline-grid;
  place-items: center;
  width: var(--icon-size);
  height: var(--icon-size);
  flex: 0 0 auto;
  color: var(--icon-color);
  vertical-align: middle;
}

.art-icon.tile {
  border-radius: 38%;
  background:
    var(--tile-sheen),
    color-mix(in srgb, var(--icon-color) 13%, transparent);
  border: 1px solid color-mix(in srgb, var(--icon-color) 24%, var(--border));
  box-shadow: var(--shadow-xs), var(--shadow-inset), 0 0 18px var(--icon-glow);
}

.art-icon svg {
  width: 78%;
  height: 78%;
  overflow: visible;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.art-icon .pearl {
  fill: color-mix(in srgb, currentColor 22%, var(--icon-pearl-mix));
  stroke: currentColor;
}

.art-icon .soft-orbit {
  fill: color-mix(in srgb, currentColor 8%, transparent);
  stroke: color-mix(in srgb, currentColor 24%, transparent);
  stroke-width: 0.8;
}

.art-icon text {
  fill: currentColor;
  stroke: none;
  font-size: 3.3px;
  font-weight: 800;
  letter-spacing: 0;
  text-anchor: middle;
}

.tone-aqua {
  --icon-color: var(--accent);
  --icon-glow: var(--accent-glow);
}

.tone-mint {
  --icon-color: var(--success);
  --icon-glow: color-mix(in srgb, var(--success) 18%, transparent);
}

.tone-pearl {
  --icon-color: var(--text-soft);
  --icon-glow: var(--accent-glow);
}

.tone-coral {
  --icon-color: var(--danger);
  --icon-glow: color-mix(in srgb, var(--danger) 16%, transparent);
}

.tone-sand {
  --icon-color: var(--warning);
  --icon-glow: color-mix(in srgb, var(--warning) 16%, transparent);
}

.tone-slate {
  --icon-color: var(--text-soft);
  --icon-glow: color-mix(in srgb, var(--text) 10%, transparent);
}

.tone-on-accent {
  --icon-color: #fff;
  --icon-glow: rgba(255, 255, 255, 0.24);
}
</style>
