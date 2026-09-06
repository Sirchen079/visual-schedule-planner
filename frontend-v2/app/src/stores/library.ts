/**
 * 资料库 store：文件列表 + 上传 + 备注编辑 + 回收站（/library、/trash 视图共用）。
 *
 * - 搜索走 GET /api/files?q（后端过滤）；软删除/恢复/清除走 trash 三件套。
 * - 软删除乐观移除 + 失败回滚（约束①）。
 * - refreshAll 供 run done 自动刷新（AI 工具 bulk_delete_files/import_web_resources 等）。
 */
import { defineStore } from 'pinia'
import type { LibraryFile } from '../api/files'
import { deleteFile, listFiles, listTrashFiles, patchFile, purgeFile, restoreFile, uploadFile } from '../api/files'

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

/** 解析状态徽标文案（实测枚举 parsed/pending；未知原样显示）。 */
export function parseStatusLabel(status: string): string {
  const map: Record<string, string> = {
    parsed: '已解析',
    pending: '待解析',
    unsupported: '不支持',
    failed: '解析失败',
  }
  return map[status] ?? status
}

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

    /** 软删除（入回收站）。乐观移除 + 失败回滚。 */
    async remove(fileId: number): Promise<boolean> {
      const items = this.items
      const idx = items?.findIndex((f) => f.id === fileId) ?? -1
      if (!items || idx < 0) return true
      const removed = items.splice(idx, 1)[0]
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

    /** 从回收站恢复：trash 列表移除；主列表已加载时头部插回（实测 restore 返回完整行）。 */
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
