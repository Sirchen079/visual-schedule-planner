import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { moodLabel, useJournalStore } from './journal'
import { humanSize, parseStatusLabel, useLibraryStore } from './library'
import type { JournalEntry } from '../api/journal'
import type { LibraryFile } from '../api/files'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => JSON.parse(text),
  } as unknown as Response
}

function makeEntry(partial: Partial<JournalEntry>): JournalEntry {
  return {
    id: 1,
    date: '2026-09-05',
    content: '测试日记',
    mood: 'calm',
    created_at: '2026-09-05T10:00:00',
    updated_at: '2026-09-05T10:00:00',
    ...partial,
  }
}

function makeFile(partial: Partial<LibraryFile>): LibraryFile {
  return {
    id: 1,
    original_name: 'm3-test.txt',
    storage_path: 'attachments\\m3-test.txt',
    size: 1024,
    mime_type: 'text/plain',
    notes: '',
    source_url: null,
    resource_type: 'file',
    parse_status: 'parsed',
    uploaded_at: '2026-09-05T10:00:00',
    ...partial,
  }
}

describe('journal store（upsert 幂等保存）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('moodLabel：预设映射，未知原样返回', () => {
    expect(moodLabel('calm')).toBe('平静')
    expect(moodLabel('custom-x')).toBe('custom-x')
    expect(moodLabel(null)).toBe('')
  })

  it('save：新日期头部插入，已有日期原位更新', async () => {
    const store = useJournalStore()
    store.entries = [makeEntry({ id: 2, date: '2026-09-03' })]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(makeEntry({ id: 3, date: '2026-09-05', content: '新页' }))),
    )
    const ok = await store.save('2026-09-05', '新页', 'calm')
    expect(ok).toBe(true)
    expect(store.entries?.map((e) => e.date)).toEqual(['2026-09-05', '2026-09-03'])
    expect(store.activeEntry?.content).toBe('新页')

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(makeEntry({ id: 3, date: '2026-09-05', content: '改过' }))),
    )
    await store.save('2026-09-05', '改过', null)
    expect(store.entries?.map((e) => e.date)).toEqual(['2026-09-05', '2026-09-03']) // 原位不重复
    expect(store.entries?.[0].content).toBe('改过')
    vi.unstubAllGlobals()
  })

  it('save 失败：actionError 可见且列表不变', async () => {
    const store = useJournalStore()
    store.entries = [makeEntry({})]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '日期无效' }, 422)))
    const ok = await store.save('2026-13-99', 'x', null)
    expect(ok).toBe(false)
    expect(store.entries).toHaveLength(1)
    expect(store.actionError).toContain('日期无效')
    vi.unstubAllGlobals()
  })

  it('refreshAll：从未加载过且无 activeDay 时不白发请求', async () => {
    const store = useJournalStore()
    const spy = vi.fn(async () => jsonResponse([]))
    vi.stubGlobal('fetch', spy)
    await store.refreshAll()
    expect(spy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})

describe('library 纯函数与 store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('humanSize：B/KB/MB/GB 边界', () => {
    expect(humanSize(0)).toBe('0 B')
    expect(humanSize(512)).toBe('512 B')
    expect(humanSize(1024)).toBe('1.0 KB')
    expect(humanSize(1536)).toBe('1.5 KB')
    expect(humanSize(14292)).toBe('14.0 KB') // 合成文档的示例大小。
    expect(humanSize(5 * 1024 * 1024)).toBe('5.0 MB')
    expect(humanSize(-1)).toBe('—')
  })

  it('parseStatusLabel：实测枚举映射，未知原样', () => {
    expect(parseStatusLabel('parsed')).toBe('已解析')
    expect(parseStatusLabel('pending')).toBe('待解析')
    expect(parseStatusLabel('weird')).toBe('weird')
  })

  it('remove：软删除乐观移除，失败回滚原位', async () => {
    const store = useLibraryStore()
    store.items = [makeFile({ id: 1 }), makeFile({ id: 2 })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'db locked' }, 500)))
    const ok = await store.remove(1)
    expect(ok).toBe(false)
    expect(store.items?.map((f) => f.id)).toEqual([1, 2])
    vi.unstubAllGlobals()
  })

  it('restore：trash 移除、主列表头部插回', async () => {
    const store = useLibraryStore()
    store.items = [makeFile({ id: 2 })]
    store.trash = [makeFile({ id: 9, original_name: '回收站文件' })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(makeFile({ id: 9 }))))
    const ok = await store.restore(9)
    expect(ok).toBe(true)
    expect(store.trash).toHaveLength(0)
    expect(store.items?.map((f) => f.id)).toEqual([9, 2])
    vi.unstubAllGlobals()
  })

  it('purge：trash 移除且不进主列表', async () => {
    const store = useLibraryStore()
    store.trash = [makeFile({ id: 9 })]
    store.items = [makeFile({ id: 2 })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(undefined, 204)))
    const ok = await store.purge(9)
    expect(ok).toBe(true)
    expect(store.trash).toHaveLength(0)
    expect(store.items?.map((f) => f.id)).toEqual([2])
    vi.unstubAllGlobals()
  })
})
