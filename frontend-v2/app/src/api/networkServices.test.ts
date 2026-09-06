import { afterEach, describe, expect, it, vi } from 'vitest'
import { defaultFetchBinding, defaultSearchBinding, getVision, getWebServices, mcpServerIssue, mcpToolIssue, parseVisionArguments, removeTavilyKey, saveTavilyKey, saveVision, saveWebServices } from './networkServices'
import type { MCPServerInfo } from './settings'

const server: MCPServerInfo = { id: 1, name: 'reader', transport: 'http', command: null, args_json: '[]', url: 'https://example.test/mcp', timeout_sec: 30, enabled: true, auto_approve_readonly: true, trusted: false, last_status: 'ok', last_error: null, created_at: '' }
function mockFetch(body: unknown = {}) { const fn = vi.fn().mockImplementation(async () => new Response(JSON.stringify(body), { status: 200 })); vi.stubGlobal('fetch', fn); return fn }
afterEach(() => vi.unstubAllGlobals())

describe('network service transport and credential isolation', () => {
  it('reads the dedicated endpoints', async () => {
    const request = mockFetch()
    await getWebServices(); await getVision()
    expect(request.mock.calls.map(c => c[0])).toEqual(['/ai/web-services', '/ai/vision'])
  })
  it('sends independent providers in a full, unwrapped config without credential fields', async () => {
    const request = mockFetch()
    const config = { search_provider: 'builtin' as const, fetch_provider: 'mcp' as const, tavily_search_depth: 'basic' as const, tavily_extract_depth: 'advanced' as const, mcp_search: null, mcp_fetch: { ...defaultFetchBinding(), server_id: 1, tool_name: 'read', url_argument: 'urls', url_as_list: true, content_path: 'results.0.raw_content' } }
    await saveWebServices(config)
    expect(request.mock.calls[0][0]).toBe('/ai/web-services')
    expect(request.mock.calls[0][1].method).toBe('PUT')
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual(config)
    expect(request.mock.calls[0][1].body).not.toMatch(/api_key|credentials/)
  })
  it('preserves a key on empty or whitespace input without issuing any request', async () => {
    const request = mockFetch()
    expect(await saveTavilyKey('')).toBeNull()
    expect(await saveTavilyKey('  \n')).toBeNull()
    expect(request).not.toHaveBeenCalled()
  })
  it('uses separate write and delete endpoints for explicit credential actions', async () => {
    const request = mockFetch({ tavily_has_api_key: true })
    await saveTavilyKey('  test-only-key  ')
    expect(request.mock.calls[0][0]).toBe('/ai/web-services/credentials/tavily')
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ api_key: 'test-only-key' })
    await removeTavilyKey()
    expect(request.mock.calls[1][1].method).toBe('DELETE')
    expect(request.mock.calls[1][1].body).toBeUndefined()
  })
  it('saves vision consent and template as JSON, with no config wrapper', async () => {
    const request = mockFetch()
    const config = { enabled: true, server_id: 1, tool_name: 'inspect', arguments: { image: '{{image_data_url}}', prompt: '{{prompt}}' } }
    await saveVision(config)
    expect(request.mock.calls[0][0]).toBe('/ai/vision')
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual(config)
  })
})

describe('MCP readiness and compatible arguments', () => {
  it('requires enabled and readonly approval; only stdio requires trust', () => {
    expect(mcpServerIssue(server)).toBe('')
    expect(mcpServerIssue(undefined)).not.toBe('')
    expect(mcpServerIssue({ ...server, enabled: false })).toContain('未启用')
    expect(mcpServerIssue({ ...server, auto_approve_readonly: false })).toContain('只读')
    expect(mcpServerIssue({ ...server, transport: 'stdio' })).toContain('受信任')
    expect(mcpServerIssue({ ...server, transport: 'stdio', trusted: true })).toBe('')
  })
  it('rejects missing or nonreadonly tools and identifies unmapped required arguments', () => {
    const tool = { name: 'search', description: '', read_only: true, input_schema: { required: ['query', 'locale'] } }
    expect(mcpToolIssue(undefined, {})).toContain('加载工具')
    expect(mcpToolIssue({ ...tool, read_only: false }, {})).toContain('未声明为只读')
    expect(mcpToolIssue(tool, { query: 'x' })).toContain('locale')
    expect(mcpToolIssue(tool, { query: 'x', locale: 'zh' })).toBe('')
  })
  it('starts with explicit field mapping defaults', () => {
    expect(defaultSearchBinding()).toMatchObject({ query_argument: 'query', limit_argument: 'max_results', results_path: 'results' })
    expect(defaultFetchBinding()).toMatchObject({ url_argument: 'url', url_as_list: false, content_path: '' })
  })
})

describe('vision parameter templates', () => {
  it('preserves nested literal types and supported placeholders', () => {
    const args = { messages: [{ image: '{{image_data_url}}', text: '{{ prompt }}' }], detail: true, count: 2, name: '{{filename}}', type: '{{mime_type}}' }
    expect(parseVisionArguments(JSON.stringify(args), server, true)).toEqual(args)
  })
  it.each(['[]', 'null', '"text"', '{broken'])('rejects non-object or invalid JSON: %s', value => {
    expect(() => parseVisionArguments(value, server, true)).toThrow(/JSON/)
  })
  it('requires image data when enabled and refuses unsupported or incomplete tokens', () => {
    expect(() => parseVisionArguments('{"prompt":"{{prompt}}"}', server, true)).toThrow('必须包含')
    for (const image of ['{{image_url}}', '{{image_data_url}', '{{IMAGE}}']) expect(() => parseVisionArguments(JSON.stringify({ image }), server, true)).toThrow()
  })
  it('only allows local paths for trusted stdio, even in disabled templates', () => {
    const args = '{"image":"{{image_path}}"}'
    expect(() => parseVisionArguments(args, server, false)).toThrow('本地 stdio')
    expect(() => parseVisionArguments(args, { ...server, transport: 'stdio' }, true)).toThrow('本地 stdio')
    expect(parseVisionArguments(args, { ...server, transport: 'stdio', trusted: true }, true)).toEqual({ image: '{{image_path}}' })
  })
  it('rejects credentials in nested mappings without echoing the supplied secret', () => {
    try { parseVisionArguments('{"image":"{{image_data_url}}","options":{"api_key":"test-secret-never-echo"}}', server, true); throw new Error('expected validation rejection') }
    catch (e) { expect(String(e)).toContain('凭据'); expect(String(e)).not.toContain('test-secret-never-echo') }
  })
})
