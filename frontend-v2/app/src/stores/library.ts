/**
 * 资料库 store：文件列表 + 上传 + 备注编辑 + 回收站（/library、/trash 视图共用）。
 *
 * - 搜索走 GET /api/files?q（后端过滤）；软删除/恢复/清除走 trash 三件套。
 * - 软删除乐观移除 + 失败回滚。
 * - md_status：Markdown 副本状态；pending（扫描页 OCR 中）由视图按 3s 轮询单文件详情，
 *   终态（done/failed）自动停表；failed 可 reparse 重建。
 * - refreshAll 供 run done 自动刷新（AI 工具 bulk_delete_files/import_web_resources 等）。
 */
import { defineStore } from 'pinia'
import type { LibraryFile } from '../api/files'
import { deleteFile, getFile, listFiles, listTrashFiles, patchFile, purgeFile, reparseFile, restoreFile, uploadFile } from '../api/files'

/** 人类可读文件大小（纯函数，单测覆盖）。 */
export function humanSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = bytes
  let i = -1
  do {
    v /= 1024
    i += 1
  } while (v >= 1024 && i < units.length - 1)
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[i]}`
}

/** 文件解析状态标签，未知状态保留原值。 */
export function parseStatusLabel(status: string): string {
  const map: Record<string, string> = {
    parsed: '已解析',
    pending: '待解析',
    unsupported: '不支持',
    failed: '解析失败',
  }
  return map[status] ?? status
}

/** Markdown 副本状态角标文案：none 不展示（返回空串），未知状态保留原值。 */
export function mdStatusLabel(status: string): string {
  const map: Record<string, string> = {
    done: '已转 Markdown',
    pending: 'OCR 识别中',
    failed: '识别失败',
  }
  return map[status] ?? (status === 'none' ? '' : status)
}

/** md_status=pending（扫描页 OCR 后台转换）的详情轮询间隔。 */
export const MD_POLL_INTERVAL_MS = 3000
/** 轮询连续失败上限：超过即停表（行保持最后已知状态，下次 load 后可再续）。 */
const MD_POLL_MAX_FAILURES = 3

/** md_status 轮询句柄（模块级：定时器无需响应式，终态/卸载即清理）。 */
const mdPollers = new Map<number, ReturnType<typeof setInterval>>()
/** 各文件连续失败计数（成功即清零）。 */
const mdPollFailures = new Map<number, number>()

export const useLibraryStore = defineStore('library', {
  state: () => ({
    items: null as LibraryFile[] | null,
    /** 当前搜索词（空 = 全部） */
    query: '',
    loading: false,
    uploading: false,
    trash: null as LibraryFile[] | null,
    loadingTrash: false,
    error: null as string | null,
    trashError: null as string | null,
    actionError: null as string | null,
    lastRefreshedAt: null as number | null,
  }),

  actions: {
    async load(q?: string): Promise<void> {
      if (q !== undefined) this.query = q
      this.loading = true
      this.error = null
      try {
        this.items = await listFiles(this.query || undefined)
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '资料库加载失败'
      } finally {
        this.loading = false
      }
    },

    async loadTrash(): Promise<void> {
      this.loadingTrash = true
      this.trashError = null
      try {
        this.trash = await listTrashFiles()
      } catch (e) {
        this.trashError = e instanceof Error ? e.message : '资料回收站加载失败'
      } finally {
        this.loadingTrash = false
      }
    },

    /** run done 后由壳层调用：只刷已加载过的数据。 */
    async refreshAll(): Promise<void> {
      const tasks: Promise<void>[] = []
      if (this.items !== null) tasks.push(this.load())
      if (this.trash !== null) tasks.push(this.loadTrash())
      await Promise.all(tasks)
    },

    /* ---- md_status：单文件同步 + pending 轮询 + 重新解析 ---- */

    /** 用新文件行原位替换列表中的同 id 行（轮询 / reparse 共用）。 */
    applyFile(row: LibraryFile): void {
      const items = this.items
      const idx = items?.findIndex((f) => f.id === row.id) ?? -1
      if (items && idx >= 0) items.splice(idx, 1, row)
    },

    /** 拉取单文件详情并写回列表；失败返回 null（由轮询方计数处理）。 */
    async refreshFile(fileId: number): Promise<LibraryFile | null> {
      try {
        const row = await getFile(fileId)
        this.applyFile(row)
        return row
      } catch {
        return null
      }
    },

    /** 文件进入 pending 后开始 3s 轮询详情；终态（done/failed）由 pollMdOnce 自动停表。 */
    startMdPolling(fileId: number): void {
      if (mdPollers.has(fileId)) return
      mdPollFailures.delete(fileId)
      const timer = setInterval(() => { void this.pollMdOnce(fileId) }, MD_POLL_INTERVAL_MS)
      mdPollers.set(fileId, timer)
    },

    /** 单次轮询：拉详情写回；到终态或连续失败超限即停表。 */
    async pollMdOnce(fileId: number): Promise<void> {
      const row = await this.refreshFile(fileId)
      if (row === null) {
        const failures = (mdPollFailures.get(fileId) ?? 0) + 1
        mdPollFailures.set(fileId, failures)
        if (failures >= MD_POLL_MAX_FAILURES) this.stopMdPolling(fileId)
        return
      }
      mdPollFailures.delete(fileId)
      if (row.md_status !== 'pending') this.stopMdPolling(fileId)
    },

    stopMdPolling(fileId: number): void {
      const timer = mdPollers.get(fileId)
      if (timer !== undefined) {
        clearInterval(timer)
        mdPollers.delete(fileId)
        mdPollFailures.delete(fileId)
      }
    },

    /** 视图卸载停止全部轮询。 */
    stopAllMdPolling(): void {
      for (const fileId of [...mdPollers.keys()]) this.stopMdPolling(fileId)
    },

    /** 按当前列表同步轮询：pending 开表、不再 pending 的停表（视图 load 后调用）。 */
    syncMdPolling(): void {
      const pending = new Set((this.items ?? []).filter((f) => f.md_status === 'pending').map((f) => f.id))
      for (const fileId of [...mdPollers.keys()]) {
        if (!pending.has(fileId)) this.stopMdPolling(fileId)
      }
      for (const fileId of pending) this.startMdPolling(fileId)
    },

    /** 重新解析（Markdown 管道升级 / OCR 失败重试）：成功后原位更新并按新状态接续轮询。 */
    async reparse(fileId: number): Promise<LibraryFile | null> {
      this.actionError = null
      try {
        const row = await reparseFile(fileId)
        this.applyFile(row)
        if (row.md_status === 'pending') this.startMdPolling(fileId)
        else this.stopMdPolling(fileId)
        return row
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '重新解析失败'
        return null
      }
    },

    async upload(file: File, notes?: string): Promise<LibraryFile | null> {
      this.uploading = true
      this.actionError = null
      try {
        const row = await uploadFile(file, notes)
        // 搜索过滤中上传的新文件可能不匹配当前 q，简单起见清空过滤重拉
        if (this.query) {
          await this.load('')
        } else if (this.items) {
          this.items = [row, ...this.items]
        } else {
          await this.load('')
        }
        return row
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '上传失败'
        return null
      } finally {
        this.uploading = false
      }
    },

    async saveNotes(fileId: number, notes: string): Promise<boolean> {
      this.actionError = null
      try {
        const updated = await patchFile(fileId, { notes })
        this.items = (this.items ?? []).map((f) => (f.id === fileId ? updated : f))
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '备注保存失败'
        return false
      }
    },

    /** 软删除（入回收站）。乐观移除 + 失败回滚；移除的文件不再轮询。 */
    async remove(fileId: number): Promise<boolean> {
      const items = this.items
      const idx = items?.findIndex((f) => f.id === fileId) ?? -1
      if (!items || idx < 0) return true
      const removed = items.splice(idx, 1)[0]
      this.stopMdPolling(fileId)
      this.actionError = null
      try {
        await deleteFile(fileId)
        return true
      } catch (e) {
        items.splice(idx, 0, removed) // 回滚
        this.actionError = e instanceof Error ? e.message : '删除失败'
        return false
      }
    },

    /** 恢复后从回收站移除，并更新已加载的主列表。 */
    async restore(fileId: number): Promise<boolean> {
      this.actionError = null
      try {
        const row = await restoreFile(fileId)
        this.trash = (this.trash ?? []).filter((f) => f.id !== fileId)
        if (this.items !== null && !this.items.some((f) => f.id === fileId)) {
          this.items = [row, ...this.items]
        }
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '恢复失败'
        return false
      }
    },

    /** 彻底删除（连物理文件，不可恢复）。 */
    async purge(fileId: number): Promise<boolean> {
      this.actionError = null
      try {
        await purgeFile(fileId)
        this.trash = (this.trash ?? []).filter((f) => f.id !== fileId)
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '彻底删除失败'
        return false
      }
    },
  },
})
