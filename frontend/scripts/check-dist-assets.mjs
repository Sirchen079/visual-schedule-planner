import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const distDir = resolve(__dirname, '../dist')
const indexPath = resolve(distDir, 'index.html')

if (!existsSync(indexPath)) {
  console.error('Missing frontend/dist/index.html. Run npm run build first.')
  process.exit(1)
}

const indexHtml = readFileSync(indexPath, 'utf8')
const assetRefs = [...indexHtml.matchAll(/\b(?:src|href)=["']\/?(assets\/[^"']+\.(?:js|css))["']/g)].map(
  (match) => match[1]
)

if (!assetRefs.length) {
  console.error('No JS/CSS asset references found in frontend/dist/index.html.')
  process.exit(1)
}

const missing = assetRefs.filter((assetRef) => !existsSync(resolve(distDir, assetRef)))

if (missing.length) {
  console.error('frontend/dist/index.html references missing assets:')
  for (const asset of missing) console.error(`- ${asset}`)
  process.exit(1)
}

const referenced = new Set(assetRefs)
const emittedAssetsDir = resolve(distDir, 'assets')
const staleAssets = existsSync(emittedAssetsDir)
  ? readdirSync(emittedAssetsDir)
      .filter((name) => /\.(?:js|css)$/.test(name))
      .map((name) => `assets/${name}`)
      .filter((asset) => !referenced.has(asset))
  : []

if (staleAssets.length) {
  console.error('frontend/dist/assets contains stale JS/CSS assets not referenced by index.html:')
  for (const asset of staleAssets) console.error(`- ${asset}`)
  process.exit(1)
}

console.log(`Dist asset check passed (${assetRefs.length} references)`)
