import fs from 'node:fs'
import { pathToFileURL } from 'node:url'
const root = 'E:/知时'
const { default: openapiTS, astToString } = await import(pathToFileURL(`${root}/frontend-v2/app/node_modules/openapi-typescript/dist/index.mjs`).href)
const schema = JSON.parse(fs.readFileSync(`${root}/backend-v2/docs/contracts/openapi.json`, 'utf8'))
fs.writeFileSync(`${root}/frontend-v2/app/src/api/contracts/rest.d.ts`, astToString(await openapiTS(schema, { defaultNonNullable: false })))
console.log('REST_CONTRACT_GENERATED')
