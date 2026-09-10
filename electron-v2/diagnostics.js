'use strict'
const fs = require('fs')
const path = require('path')

const events = new Set(['startup', 'backend_started', 'backend_exit', 'backend_ready', 'startup_failed',
  'window_loaded', 'window_load_failed', 'renderer_gone', 'unresponsive', 'update_install_failed', 'shutdown'])

function createDiagnostics(dataRoot, version) {
  const file = path.join(dataRoot, 'v2', 'logs', 'desktop-diagnostics.jsonl')
  return (event, code) => {
    if (!events.has(event)) return
    try {
      fs.mkdirSync(path.dirname(file), { recursive: true })
      if (fs.existsSync(file) && fs.statSync(file).size > 512 * 1024) {
        if (fs.existsSync(file + '.1')) fs.unlinkSync(file + '.1')
        fs.renameSync(file, file + '.1')
      }
      const row = { kind: 'desktop', time: new Date().toISOString(), event,
        version: /^\d+\.\d+\.\d+$/.test(version) ? version : 'unknown' }
      if (Number.isInteger(code)) row.status_code = code
      fs.appendFileSync(file, JSON.stringify(row) + '\n', 'utf8')
    } catch { /* Logging failure must not prevent startup or shutdown. */ }
  }
}

module.exports = { createDiagnostics }
