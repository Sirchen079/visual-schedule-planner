// SVG is the editable source. Preserve alpha and include native Windows icon sizes.
const { app, BrowserWindow } = require('electron')
const fs = require('fs')
const path = require('path')
const OUT_DIR = path.join(__dirname, '..', 'assets')
function pngsToIco(images) {
  const header = Buffer.alloc(6)
  header.writeUInt16LE(1, 2); header.writeUInt16LE(images.length, 4)
  let offset = 6 + 16 * images.length
  const entries = images.map(({ size, png }) => {
    const entry = Buffer.alloc(16)
    entry[0] = entry[1] = size === 256 ? 0 : size
    entry.writeUInt16LE(1, 4); entry.writeUInt16LE(32, 6)
    entry.writeUInt32LE(png.length, 8); entry.writeUInt32LE(offset, 12)
    offset += png.length
    return entry
  })
  return Buffer.concat([header, ...entries, ...images.map(i => i.png)])
}
app.whenReady().then(async () => {
  const svg = fs.readFileSync(path.join(OUT_DIR, 'icon.svg'), 'utf8')
  const win = new BrowserWindow({ width: 512, height: 512, show: false, frame: false,
    transparent: true, backgroundColor: '#00000000',
    webPreferences: { offscreen: true, contextIsolation: true, nodeIntegration: false, sandbox: true } })
  await win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
    '<html><body style="margin:0;background:transparent">' + svg + '</body></html>'))
  await win.webContents.executeJavaScript('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
  const full = await win.webContents.capturePage({ x: 0, y: 0, width: 512, height: 512 })
  const images = [16, 24, 32, 48, 64, 128, 256].map(size => ({ size,
    png: full.resize({ width: size, height: size, quality: 'best' }).toPNG() }))
  fs.writeFileSync(path.join(OUT_DIR, 'icon.png'), images.at(-1).png)
  fs.writeFileSync(path.join(OUT_DIR, 'tray.png'), images.find(i => i.size === 32).png)
  fs.writeFileSync(path.join(OUT_DIR, 'icon.ico'), pngsToIco(images))
  console.log('[gen-icon] transparent PNG and 7-size ICO generated')
  win.destroy(); app.exit(0)
}).catch(e => { console.error(e); app.exit(1) })
