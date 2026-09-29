import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import * as foldersApi from '../api/conversationFolders'
import { useConversationStore } from './conversation'

// 文件夹端点整体 mock：store 行为（守卫/置位/入列/移除）不依赖真实 http。
vi.mock('../api/conversationFolders', () => ({
  listFolders: vi.fn(),
  attachFolder: vi.fn(),
  detachFolder: vi.fn(),
}))

/** select() 里的历史拉取走真实 fetch（../api/ai 未 mock）：node 环境用 JSON 响应替身兜住。 */
function stubFetchJson(payload: unknown): void {
  const text = JSON.stringify(payload)
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, text: async () => text, json: async () => payload,
  } as unknown as Response)))
}

const FOLDER = { id: 3, label: 'demo', root_path: 'E:/demo', created_at: '2026-09-29T00:00:00' }

describe('conversation folders（对话文件夹附件）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('loadFolders：activeId=7 拉取置入；activeId=null 清空且不调 api', async () => {
    const conv = useConversationStore()
    conv.activeId = 7
    vi.mocked(foldersApi.listFolders).mockResolvedValue([FOLDER])
    await conv.loadFolders()
    expect(foldersApi.listFolders).toHaveBeenCalledWith(7)
    expect(conv.folders).toEqual([FOLDER])

    conv.activeId = null
    await conv.loadFolders()
    expect(conv.folders).toEqual([])
    expect(foldersApi.listFolders).toHaveBeenCalledTimes(1) // null 分支不拉取
  })

  it('select 接线：会话加载完成后 folders 随之置位', async () => {
    stubFetchJson([])
    vi.mocked(foldersApi.listFolders).mockResolvedValue([FOLDER])
    const conv = useConversationStore()
    await conv.select(7)
    expect(conv.activeId).toBe(7)
    expect(foldersApi.listFolders).toHaveBeenCalledWith(7)
    expect(conv.folders).toEqual([FOLDER])
  })

  it('attachFolder：以 (7, 路径) 调 api 且返回行进 folders；抛错置 error 且 folders 不变', async () => {
    const conv = useConversationStore()
    conv.activeId = 7
    vi.mocked(foldersApi.attachFolder).mockResolvedValue(FOLDER)
    await conv.attachFolder('E:/demo')
    expect(foldersApi.attachFolder).toHaveBeenCalledWith(7, 'E:/demo')
    expect(conv.folders).toEqual([FOLDER])

    vi.mocked(foldersApi.attachFolder).mockRejectedValueOnce(new Error('目录不存在'))
    await conv.attachFolder('E:/missing')
    expect(conv.error).toContain('目录不存在')
    expect(conv.folders).toEqual([FOLDER]) // 失败不入列
  })

  it('detachFolder：以 (7, id) 调 api 且该行移除', async () => {
    const conv = useConversationStore()
    conv.activeId = 7
    conv.folders = [FOLDER]
    vi.mocked(foldersApi.detachFolder).mockResolvedValue(undefined)
    await conv.detachFolder(3)
    expect(foldersApi.detachFolder).toHaveBeenCalledWith(7, 3)
    expect(conv.folders).toEqual([])
  })

  it('activeId=null 时 attach/detach 直接置 error 返回，不调 api', async () => {
    const conv = useConversationStore()
    conv.activeId = null
    await conv.attachFolder('E:/x')
    await conv.detachFolder(3)
    expect(conv.error).toBeTruthy()
    expect(foldersApi.attachFolder).not.toHaveBeenCalled()
    expect(foldersApi.detachFolder).not.toHaveBeenCalled()
  })
})
