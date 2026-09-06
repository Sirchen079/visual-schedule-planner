/**
 * 报表 store：/ai/reports 列表 + 生成 + 删除。
 * 列表接口本身即返回全文 content（无独立瘦身列表），因此选中详情直接从列表项取，不二次请求。
 * 过滤走服务端 report_type 查询参数；生成/删除成功后本地增量维护，避免整列表重拉闪烁。
 */
import { defineStore } from 'pinia'
import {
  createReport,
  deleteReport,
  listReports,
  type GeneratableReportType,
  type Report,
  type ReportType,
} from '../api/reports'

export type ReportFilter = ReportType | 'all'

interface ReportsState {
  reports: Report[] | null
  filter: ReportFilter
  selectedId: number | null
  loading: boolean
  error: string | null
  /** 正在生成中的类型（daily/weekly 各最多一个进行中） */
  generating: GeneratableReportType[]
  /** 正在删除中的报表 id */
  deleting: number[]
  actionError: string | null
}

export const useReportsStore = defineStore('reports', {
  state: (): ReportsState => ({
    reports: null,
    filter: 'all',
    selectedId: null,
    loading: false,
    error: null,
    generating: [],
    deleting: [],
    actionError: null,
  }),
  getters: {
    selected(state): Report | null {
      return state.reports?.find((r) => r.id === state.selectedId) ?? null
    },
  },
  actions: {
    async load(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        const rows = await listReports(this.filter === 'all' ? undefined : this.filter)
        this.reports = rows
        // 选中项若被过滤掉/已删除，回落到列表首条
        if (this.selectedId !== null && !rows.some((r) => r.id === this.selectedId)) {
          this.selectedId = rows[0]?.id ?? null
        }
        if (this.selectedId === null && rows.length > 0) this.selectedId = rows[0].id
      } catch (e) {
        this.error = e instanceof Error ? e.message : '报表加载失败'
      } finally {
        this.loading = false
      }
    },

    async setFilter(filter: ReportFilter): Promise<void> {
      if (filter === this.filter) return
      this.filter = filter
      await this.load()
    },

    select(id: number): void {
      this.selectedId = id
    },

    /** 生成日报/周报；成功则插入列表头部并选中。失败（400/422）只落 actionError，由视图呈现可重试。 */
    async generate(reportType: GeneratableReportType, targetDate?: string): Promise<void> {
      if (this.generating.includes(reportType)) return
      this.generating = [...this.generating, reportType]
      this.actionError = null
      try {
        const row = await createReport(reportType, targetDate)
        const rest = (this.reports ?? []).filter((r) => r.id !== row.id)
        this.reports = [row, ...rest]
        if (this.filter === 'all' || this.filter === row.report_type) this.selectedId = row.id
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '报表生成失败'
      } finally {
        this.generating = this.generating.filter((t) => t !== reportType)
      }
    },

    async remove(id: number): Promise<void> {
      if (this.deleting.includes(id)) return
      this.deleting = [...this.deleting, id]
      this.actionError = null
      try {
        await deleteReport(id)
        const rest = (this.reports ?? []).filter((r) => r.id !== id)
        this.reports = rest
        if (this.selectedId === id) this.selectedId = rest[0]?.id ?? null
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '删除失败'
      } finally {
        this.deleting = this.deleting.filter((x) => x !== id)
      }
    },
  },
})
