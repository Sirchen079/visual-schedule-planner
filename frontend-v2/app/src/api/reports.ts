/**
 * AI 报表（晨报/日报/周报）客户端。
 * 契约：/ai/reports 系列响应已 typed（ReportOut），Report 直接派生自 contracts 生成类型，
 * 不再手写字段。已核实行为：
 * - 列表：GET /ai/reports?report_type=&limit= → 数组，按 id 倒序；limit 收敛到 1..200（默认 50）
 * - 生成：POST /ai/reports/{daily|weekly}，body {target_date?}（缺省 = 今天）；
 *   无启用 AI 配置 → 400；report_type 非法 / LLM 调用失败 → 422（额度耗尽期间会持续 422，UI 须可重试）
 * - 晨报（briefing）不接受 POST 生成，由 GET /ai/briefing/today 同日幂等产出（规则降级恒 200）
 * - 删除：DELETE /ai/reports/{id} → 204；不存在 → 404
 */
import type { components } from './contracts/rest'
import { http } from './http'

export type ReportType = 'briefing' | 'daily' | 'weekly'

/** 可手动生成的类型（briefing 只能由 /ai/briefing/today 幂等产出） */
export type GeneratableReportType = Exclude<ReportType, 'briefing'>

/** 报表实形 = 生成 ReportOut。report_type 后端为自由串，入参侧仍用上面的字面量联合收窄。 */
export type Report = components['schemas']['ReportOut']

export function listReports(reportType?: ReportType, limit = 50): Promise<Report[]> {
  return http.get('/ai/reports', { report_type: reportType, limit })
}

export function createReport(reportType: GeneratableReportType, targetDate?: string): Promise<Report> {
  return http.post(`/ai/reports/${reportType}`, targetDate ? { target_date: targetDate } : undefined)
}

export function deleteReport(reportId: number): Promise<void> {
  return http.del(`/ai/reports/${reportId}`)
}
