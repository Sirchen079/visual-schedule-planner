import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { readAutonomy, useSettingsStore } from './settings'
import type { AiConfigInfo, Grant, MCPServerInfo, SkillInfo } from '../api/settings'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = payload === undefined ? '' : JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => (text ? JSON.parse(text) : undefined),
  } as unknown as Response
}

function makeGrant(partial: Partial<Grant>): Grant {
  return { id: 1, tool_name: 'delete_event', arg_pattern: '*', created_at: '2026-09-05T01:00:00', ...partial }
}

function makeMcp(partial: Partial<MCPServerInfo>): MCPServerInfo {
  return {
    id: 1,
    name: 'fs',
    transport: 'http',
    command: '',
    args_json: '[]',
    url: 'http://127.0.0.1:9000/mcp',
    timeout_sec: 30,
    enabled: false,
    auto_approve_readonly: false,
    trusted: false,
    last_status: 'untested',
    last_error: null,
    created_at: '2026-09-05T01:00:00',
    ...partial,
  }
}

function makeConfig(partial: Partial<AiConfigInfo>): AiConfigInfo {
  return {
    id: 1,
    name: 'cfg-a',
    provider_kind: 'openai_compat',
    model: 'glm-4-flash',
    base_url: 'https://api.example.com/v4',
    enabled: false,
    ...partial,
  }
}

function makeSkill(partial: Partial<SkillInfo>): SkillInfo {
  return { id: 1, name: '技能', description: '', enabled: false, is_builtin: false, ...partial }
}

describe('readAutonomy 纯函数', () => {
  it('careful 原样识别；缺失/非法值回落 standard', () => {
    expect(readAutonomy({ agent_autonomy: 'careful' })).toBe('careful')
    expect(readAutonomy({ agent_autonomy: 'standard' })).toBe('standard')
    expect(readAutonomy({ agent_autonomy: 'yolo' })).toBe('standard')
    expect(readAutonomy(null)).toBe('standard')
    expect(readAutonomy({})).toBe('standard')
  })
})

describe('settings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loadSettings 成功：平铺表落定，getter 读出已知键', async () => {
    const store = useSettingsStore()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ agent_autonomy: 'careful', working_hours_start: '08:30', daily_capacity_minutes: '360' }),
      ),
    )
    await store.loadSettings()
    expect(store.autonomy).toBe('careful')
    expect(store.workingHoursStart).toBe('08:30')
    expect(store.dailyCapacity).toBe('360')
    expect(store.settingsError).toBeNull()
    vi.unstubAllGlobals()
  })

  it('loadSettings 失败：settingsError 可见', async () => {
    const store = useSettingsStore()
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '炸了' }, 500)))
    await store.loadSettings()
    expect(store.settingsError).toBe('炸了')
    expect(store.settings).toBeNull()
    vi.unstubAllGlobals()
  })

  it('setAutonomy：PUT 体为 {settings: patch}，以回包全量落定', async () => {
    const store = useSettingsStore()
    store.settings = { agent_autonomy: 'standard' }
    const spy = vi.fn(async (_url: unknown, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({ settings: { agent_autonomy: 'careful' } })
      expect(init?.method).toBe('PUT')
      return jsonResponse({ agent_autonomy: 'careful' })
    })
    vi.stubGlobal('fetch', spy)
    const ok = await store.setAutonomy('careful')
    expect(ok).toBe(true)
    expect(store.autonomy).toBe('careful')
    expect(store.savingKeys).toEqual([])
    vi.unstubAllGlobals()
  })

  it('setAutonomy 失败：actionError 可见，原档位不被篡改', async () => {
    const store = useSettingsStore()
    store.settings = { agent_autonomy: 'standard' }
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '只读键' }, 422)))
    const ok = await store.setAutonomy('careful')
    expect(ok).toBe(false)
    expect(store.autonomy).toBe('standard')
    expect(store.actionError).toContain('设置未保存')
    vi.unstubAllGlobals()
  })

  it('revokeGrant 成功：授权出列；失败保留且 actionError 可见', async () => {
    const store = useSettingsStore()
    store.grants = [makeGrant({ id: 7 }), makeGrant({ id: 8 })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(undefined, 204)))
    expect(await store.revokeGrant(7)).toBe(true)
    expect(store.grants?.map((g: Grant) => g.id)).toEqual([8])
    vi.unstubAllGlobals()

    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '不存在' }, 404)))
    expect(await store.revokeGrant(8)).toBe(false)
    expect(store.grants?.map((g: Grant) => g.id)).toEqual([8])
    expect(store.actionError).toContain('收回失败')
    vi.unstubAllGlobals()
  })

  it('toggleMcpServer：显式传目标态，以回包 enabled 落定', async () => {
    const store = useSettingsStore()
    store.mcpServers = [makeMcp({ id: 3, enabled: false })]
    const spy = vi.fn(async (_url: unknown, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({ enabled: true })
      return jsonResponse({ ok: true, enabled: true })
    })
    vi.stubGlobal('fetch', spy)
    expect(await store.toggleMcpServer(3, true)).toBe(true)
    expect(store.mcpServers?.[0].enabled).toBe(true)
    vi.unstubAllGlobals()
  })

  it('toggleMcpServer 失败：原状态不变且 actionError 可见', async () => {
    const store = useSettingsStore()
    store.mcpServers = [makeMcp({ id: 3, enabled: true })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '服务器忙' }, 500)))
    expect(await store.toggleMcpServer(3, false)).toBe(false)
    expect(store.mcpServers?.[0].enabled).toBe(true)
    expect(store.actionError).toContain('切换失败')
    vi.unstubAllGlobals()
  })

  it('addMcpServer：POST 完整 MCPServerBody，201 只回 {id} 故重拉列表落定', async () => {
    const store = useSettingsStore()
    const body = {
      name: 'fs',
      transport: 'http',
      command: '',
      args_json: '[]',
      env_json: '{}',
      url: 'http://127.0.0.1:9000/mcp',
      headers_json: '{}',
      timeout_sec: 30,
      enabled: false,
      auto_approve_readonly: false,
      trusted: false,
    }
    const spy = vi.fn(async (url: unknown, init?: RequestInit) => {
      if (init?.method === 'POST') {
        expect(String(url)).toBe('/ai/mcp/servers')
        expect(JSON.parse(String(init.body))).toEqual(body)
        return jsonResponse({ id: 9 }, 201)
      }
      return jsonResponse([makeMcp({ id: 9, name: 'fs' })])
    })
    vi.stubGlobal('fetch', spy)
    expect(await store.addMcpServer(body)).toBe(true)
    expect(spy).toHaveBeenCalledTimes(2)
    expect(store.mcpServers?.map((s) => s.id)).toEqual([9])
    expect(store.actionError).toBeNull()
    vi.unstubAllGlobals()
  })

  it('addMcpServer 失败：actionError 可见，列表不被重拉篡改', async () => {
    const store = useSettingsStore()
    store.mcpServers = [makeMcp({ id: 1 })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '名称重复' }, 422)))
    expect(await store.addMcpServer({} as Parameters<typeof store.addMcpServer>[0])).toBe(false)
    expect(store.mcpServers?.map((s) => s.id)).toEqual([1])
    expect(store.actionError).toContain('添加失败')
    vi.unstubAllGlobals()
  })

  it('saveMcpServer：PUT 部分补丁，以回包完整对象替换行', async () => {
    const store = useSettingsStore()
    store.mcpServers = [makeMcp({ id: 3, name: '旧名', timeout_sec: 30 })]
    const spy = vi.fn(async (url: unknown, init?: RequestInit) => {
      expect(String(url)).toBe('/ai/mcp/servers/3')
      expect(init?.method).toBe('PUT')
      expect(JSON.parse(String(init?.body))).toEqual({ name: '新名', timeout_sec: 60 })
      return jsonResponse(makeMcp({ id: 3, name: '新名', timeout_sec: 60 }))
    })
    vi.stubGlobal('fetch', spy)
    expect(await store.saveMcpServer(3, { name: '新名', timeout_sec: 60 })).toBe(true)
    expect(store.mcpServers?.[0].name).toBe('新名')
    expect(store.mcpServers?.[0].timeout_sec).toBe(60)
    vi.unstubAllGlobals()
  })

  it('removeMcpServer 成功：行出列；失败保留且 actionError 可见', async () => {
    const store = useSettingsStore()
    store.mcpServers = [makeMcp({ id: 3 }), makeMcp({ id: 4 })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(undefined, 204)))
    expect(await store.removeMcpServer(3)).toBe(true)
    expect(store.mcpServers?.map((s) => s.id)).toEqual([4])
    vi.unstubAllGlobals()

    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '不存在' }, 404)))
    expect(await store.removeMcpServer(4)).toBe(false)
    expect(store.mcpServers?.map((s) => s.id)).toEqual([4])
    expect(store.actionError).toContain('删除失败')
    vi.unstubAllGlobals()
  })

  it('testMcpConnection 成功：回包整存，行 last_status 同步为 ok', async () => {
    const store = useSettingsStore()
    store.mcpServers = [makeMcp({ id: 3, last_status: 'untested' })]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ ok: true, tool_count: 2, tools: [{ name: 'read', description: '读' }] }),
      ),
    )
    expect(await store.testMcpConnection(3)).toBe(true)
    expect(store.mcpTestResults[3]).toMatchObject({ ok: true, tool_count: 2 })
    expect(store.mcpServers?.[0].last_status).toBe('ok')
    expect(store.mcpServers?.[0].last_error).toBeNull()
    vi.unstubAllGlobals()
  })

  it('testMcpConnection 业务失败也是 200：ok:false 落 last_status=error 与 last_error', async () => {
    const store = useSettingsStore()
    store.mcpServers = [makeMcp({ id: 3, last_status: 'ok' })]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ ok: false, error: 'ECONNREFUSED', tool_count: 0 })),
    )
    expect(await store.testMcpConnection(3)).toBe(false)
    expect(store.mcpTestResults[3]).toMatchObject({ ok: false, error: 'ECONNREFUSED' })
    expect(store.mcpServers?.[0].last_status).toBe('error')
    expect(store.mcpServers?.[0].last_error).toBe('ECONNREFUSED')
    vi.unstubAllGlobals()
  })

  it('testMcpConnection HTTP 失败（untrusted stdio 403）：actionError 可见', async () => {
    const store = useSettingsStore()
    store.mcpServers = [makeMcp({ id: 5, transport: 'stdio', command: 'rm', url: null })]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ detail: 'stdio MCP 服务器需先在配置中显式信任（trusted=true）后才能连接' }, 403),
      ),
    )
    expect(await store.testMcpConnection(5)).toBe(false)
    expect(store.actionError).toContain('测试失败')
    expect(store.actionError).toContain('信任')
    vi.unstubAllGlobals()
  })

  it('loadMcpTools 成功缓存；失败落 mcpToolErrors 供行内重试', async () => {
    const store = useSettingsStore()
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse([{ name: 'read', description: '读文件' }])))
    await store.loadMcpTools(3)
    expect(store.mcpTools[3]).toEqual([{ name: 'read', description: '读文件' }])
    expect(store.mcpToolErrors[3]).toBe('')
    vi.unstubAllGlobals()

    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '目标连接失败' }, 502)))
    await store.loadMcpTools(3)
    expect(store.mcpToolErrors[3]).toBe('目标连接失败')
    vi.unstubAllGlobals()
  })

  it('loadConfigs 成功落定；addConfig POST 体含 api_key（仅写入一次）且创建后重拉', async () => {
    const store = useSettingsStore()
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse([makeConfig({ id: 1, enabled: true })])))
    await store.loadConfigs()
    expect(store.configs?.length).toBe(1)
    expect(store.configsError).toBeNull()
    vi.unstubAllGlobals()

    const spy = vi.fn(async (url: unknown, init?: RequestInit) => {
      if (init?.method === 'POST') {
        expect(String(url)).toBe('/ai/configs')
        expect(JSON.parse(String(init.body))).toEqual({
          name: 'cfg-b',
          provider_kind: 'openai_compat',
          model: 'glm-4-flash',
          base_url: 'https://api.example.com/v4',
          api_key: 'sk-secret',
          price_input: 0,
          price_output: 0,
          request_limit: 0,
        })
        return jsonResponse({ id: 2 }, 201)
      }
      return jsonResponse([makeConfig({ id: 1, enabled: true }), makeConfig({ id: 2, name: 'cfg-b' })])
    })
    vi.stubGlobal('fetch', spy)
    expect(
      await store.addConfig({
        name: 'cfg-b',
        provider_kind: 'openai_compat',
        model: 'glm-4-flash',
        base_url: 'https://api.example.com/v4',
        api_key: 'sk-secret',
        price_input: 0,
        price_output: 0,
        request_limit: 0,
      }),
    ).toBe(true)
    expect(spy).toHaveBeenCalledTimes(2)
    expect(store.configs?.map((c) => c.id)).toEqual([1, 2])
    vi.unstubAllGlobals()
  })

  it('enableConfig 单启用语义：目标启用、其余全部未启用（本地落定）', async () => {
    const store = useSettingsStore()
    store.configs = [makeConfig({ id: 1, enabled: true }), makeConfig({ id: 2, enabled: false })]
    const spy = vi.fn(async (url: unknown, init?: RequestInit) => {
      expect(String(url)).toBe('/ai/configs/2/enable')
      expect(init?.method).toBe('POST')
      expect(init?.body).toBeUndefined()
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', spy)
    expect(await store.enableConfig(2)).toBe(true)
    expect(store.configs?.find((c) => c.id === 1)?.enabled).toBe(false)
    expect(store.configs?.find((c) => c.id === 2)?.enabled).toBe(true)
    vi.unstubAllGlobals()
  })

  it('enableConfig 失败：原启用关系不变且 actionError 可见', async () => {
    const store = useSettingsStore()
    store.configs = [makeConfig({ id: 1, enabled: true }), makeConfig({ id: 2, enabled: false })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '配置不存在' }, 404)))
    expect(await store.enableConfig(2)).toBe(false)
    expect(store.configs?.find((c) => c.id === 1)?.enabled).toBe(true)
    expect(store.configs?.find((c) => c.id === 2)?.enabled).toBe(false)
    expect(store.actionError).toContain('启用失败')
    vi.unstubAllGlobals()
  })

  it('loadSkills 成功落定；addSkill POST enabled=false 且创建后重拉', async () => {
    const store = useSettingsStore()
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse([makeSkill({ id: 1, is_builtin: true, enabled: true })])))
    await store.loadSkills()
    expect(store.skills?.length).toBe(1)
    vi.unstubAllGlobals()

    const spy = vi.fn(async (url: unknown, init?: RequestInit) => {
      if (init?.method === 'POST') {
        expect(String(url)).toBe('/ai/skills')
        expect(JSON.parse(String(init.body))).toEqual({
          name: '周报偏好',
          description: '写周报的口味',
          content: '正文…',
          enabled: false,
        })
        return jsonResponse({ id: 7 }, 201)
      }
      return jsonResponse([
        makeSkill({ id: 1, is_builtin: true, enabled: true }),
        makeSkill({ id: 7, name: '周报偏好' }),
      ])
    })
    vi.stubGlobal('fetch', spy)
    expect(
      await store.addSkill({ name: '周报偏好', description: '写周报的口味', content: '正文…', enabled: false }),
    ).toBe(true)
    expect(spy).toHaveBeenCalledTimes(2)
    expect(store.skills?.map((s) => s.id)).toEqual([1, 7])
    vi.unstubAllGlobals()
  })

  it('activateSkill 单选激活：其余用户技能停用、内置技能不动', async () => {
    const store = useSettingsStore()
    store.skills = [
      makeSkill({ id: 1, is_builtin: true, enabled: true }),
      makeSkill({ id: 2, enabled: true }),
      makeSkill({ id: 3, enabled: false }),
    ]
    const spy = vi.fn(async (url: unknown, init?: RequestInit) => {
      expect(String(url)).toBe('/ai/skills/3/enable')
      expect(init?.method).toBe('POST')
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', spy)
    expect(await store.activateSkill(3)).toBe(true)
    expect(store.skills?.find((s) => s.id === 1)?.enabled).toBe(true) // 内置不受影响
    expect(store.skills?.find((s) => s.id === 2)?.enabled).toBe(false)
    expect(store.skills?.find((s) => s.id === 3)?.enabled).toBe(true)
    vi.unstubAllGlobals()
  })

  it('activateSkill 内置 id → 404：actionError 透出后端文案，列表不变', async () => {
    const store = useSettingsStore()
    store.skills = [makeSkill({ id: 1, is_builtin: true, enabled: true }), makeSkill({ id: 2, enabled: true })]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: '技能不存在或为内置技能' }, 404)),
    )
    expect(await store.activateSkill(1)).toBe(false)
    expect(store.actionError).toContain('技能不存在或为内置技能')
    expect(store.skills?.find((s) => s.id === 2)?.enabled).toBe(true)
    vi.unstubAllGlobals()
  })

  it('removeSkill 成功：用户技能出列；失败保留且 actionError 可见', async () => {
    const store = useSettingsStore()
    store.skills = [makeSkill({ id: 1, is_builtin: true, enabled: true }), makeSkill({ id: 2 })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(undefined, 204)))
    expect(await store.removeSkill(2)).toBe(true)
    expect(store.skills?.map((s) => s.id)).toEqual([1])
    vi.unstubAllGlobals()

    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '技能不存在或为内置技能' }, 404)))
    expect(await store.removeSkill(1)).toBe(false)
    expect(store.skills?.map((s) => s.id)).toEqual([1])
    expect(store.actionError).toContain('删除失败')
    vi.unstubAllGlobals()
  })

  it('deactivateActiveSkill：用户技能全部停用、内置不动；POST /ai/skills/disable-active', async () => {
    const store = useSettingsStore()
    store.skills = [
      makeSkill({ id: 1, is_builtin: true, enabled: true }),
      makeSkill({ id: 2, enabled: true }),
      makeSkill({ id: 3, enabled: false }),
    ]
    const spy = vi.fn(async (url: unknown, init?: RequestInit) => {
      expect(String(url)).toBe('/ai/skills/disable-active')
      expect(init?.method).toBe('POST')
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', spy)
    expect(await store.deactivateActiveSkill()).toBe(true)
    expect(store.skills?.find((s) => s.id === 1)?.enabled).toBe(true) // 内置不受影响
    expect(store.skills?.find((s) => s.id === 2)?.enabled).toBe(false)
    expect(store.skills?.find((s) => s.id === 3)?.enabled).toBe(false)
    vi.unstubAllGlobals()

    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'boom' }, 500)))
    store.skills = [makeSkill({ id: 2, enabled: true })]
    expect(await store.deactivateActiveSkill()).toBe(false)
    expect(store.skills?.find((s) => s.id === 2)?.enabled).toBe(true) // 失败不偷改
    expect(store.actionError).toContain('停用失败')
    vi.unstubAllGlobals()
  })
})

describe('主题跨端口持久化（ui.theme 契约）', () => {
  let dataset: Record<string, string>
  let storage: Record<string, string>

  beforeEach(() => {
    setActivePinia(createPinia())
    dataset = {}
    storage = {}
    vi.stubGlobal('document', { documentElement: { dataset } })
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => storage[k] ?? null,
      setItem: (k: string, v: string) => { storage[k] = v },
    })
  })

  it('reconcileTheme：远端 light 与本地 dark 不一致 → 以远端为准重刷并写缓存', async () => {
    dataset.theme = 'dark'
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ 'ui.theme': 'light' })))
    await useSettingsStore().reconcileTheme()
    expect(dataset.theme).toBe('light')
    expect(storage['zhishi-theme']).toBe('light')
    vi.unstubAllGlobals()
  })

  it('reconcileTheme：远端与本地一致 → 不动 DOM/缓存，也不写后端', async () => {
    dataset.theme = 'dark'
    const noOp = vi.fn(async () => jsonResponse({ 'ui.theme': 'dark' }))
    vi.stubGlobal('fetch', noOp)
    await useSettingsStore().reconcileTheme()
    expect(dataset.theme).toBe('dark')
    expect(storage['zhishi-theme']).toBeUndefined()
    expect(noOp).toHaveBeenCalledTimes(1) // 只有 GET，无播种
    vi.unstubAllGlobals()
  })

  it('reconcileTheme：远端缺键且本地 light → 播种回后端（升级前已选浅色不丢）', async () => {
    dataset.theme = 'light'
    const spy = vi.fn(async (_url: unknown, init?: RequestInit) =>
      init?.method === 'PUT'
        ? jsonResponse({ 'ui.theme': 'light' })
        : jsonResponse({}))
    vi.stubGlobal('fetch', spy)
    await useSettingsStore().reconcileTheme()
    const put = spy.mock.calls.map((c) => c[1]).find((i) => (i as RequestInit)?.method === 'PUT')
    expect(JSON.parse(String((put as RequestInit).body))).toEqual({ settings: { 'ui.theme': 'light' } })
    vi.unstubAllGlobals()
  })

  it('reconcileTheme：后端不可达 → 静默保持本地主题', async () => {
    dataset.theme = 'light'
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '炸了' }, 500)))
    await useSettingsStore().reconcileTheme() // 不抛
    expect(dataset.theme).toBe('light')
    vi.unstubAllGlobals()
  })

  it('saveThemePref：PUT 携带 ui.theme 并以回包全量落定；失败静默', async () => {
    const store = useSettingsStore()
    store.settings = { working_hours_start: '09:00' }
    const spy = vi.fn(async (_url: unknown, init?: RequestInit) => {
      expect(init?.method).toBe('PUT')
      expect(JSON.parse(String(init?.body))).toEqual({ settings: { 'ui.theme': 'light' } })
      return jsonResponse({ working_hours_start: '09:00', 'ui.theme': 'light' })
    })
    vi.stubGlobal('fetch', spy)
    await store.saveThemePref('light')
    expect(store.settings?.['ui.theme']).toBe('light')
    vi.unstubAllGlobals()

    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '服务器忙' }, 500)))
    await store.saveThemePref('dark') // 不抛、不进 actionError（UI 偏好不落库不阻塞）
    expect(store.actionError).toBeNull()
    vi.unstubAllGlobals()
  })
})
