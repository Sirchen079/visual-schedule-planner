import type { App } from 'vue'

const types = new Set(['Error', 'TypeError', 'RangeError', 'ReferenceError', 'SyntaxError', 'URIError', 'EvalError', 'DOMException'])
let sent = 0
function report(event: string, error?: unknown, filename = '', line = 0, column = 0) {
  // Error text, component data and page URLs may contain personal information.
  // Only send technical locations to this application's local backend.
  if (sent >= 30) return
  sent++
  if (!filename && error instanceof Error) {
    // Extract a bundle location only; the stack's first line contains the message.
    for (const frame of (error.stack || '').split('\n').slice(1)) {
      const match = frame.match(/(https?:\/\/[^\s)]+\/assets\/[A-Za-z0-9_-]+\.js):(\d+):(\d+)/)
      if (match) { filename = match[1]!; line = Number(match[2]); column = Number(match[3]); break }
    }
  }
  let asset = ''
  try {
    const url = new URL(filename || '', location.href)
    if (url.origin === location.origin && /^\/assets\/[A-Za-z0-9_-]+\.(js|css)$/.test(url.pathname)) {
      asset = url.pathname.split('/').pop() || ''
    }
  } catch { /* No URL is retained. */ }
  const name = error instanceof Error && types.has(error.name) ? error.name : 'Unknown'
  void fetch('/api/diagnostics/frontend', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event, error_type: name, asset, line, column }),
  }).catch(() => { /* Diagnostics must never create another error loop. */ })
}

export function installDiagnostics(app: App) {
  const previous = app.config.errorHandler
  app.config.errorHandler = (error, instance, info) => {
    report('vue_error', error)
    if (previous) previous(error, instance, info)
    else console.error(error)
  }
  window.addEventListener('error', event => {
    if (event instanceof ErrorEvent) report('window_error', event.error, event.filename, event.lineno, event.colno)
    else report('resource_error')
  }, true)
  window.addEventListener('unhandledrejection', event => report('unhandled_rejection', event.reason))
}
