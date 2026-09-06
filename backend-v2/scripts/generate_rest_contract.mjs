import fs from 'node:fs'

const { default: openapiTS, astToString } = await import(
  new URL('../../frontend-v2/app/node_modules/openapi-typescript/dist/index.mjs', import.meta.url).href
)
const schema = JSON.parse(fs.readFileSync(new URL('../docs/contracts/openapi.json', import.meta.url), 'utf8'))
const output = new URL('../../frontend-v2/app/src/api/contracts/rest.d.ts', import.meta.url)
fs.writeFileSync(output, astToString(await openapiTS(schema, { defaultNonNullable: false })))
console.log('REST types generated')
