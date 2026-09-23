/**
 * 运行中插话（Codex 式 steering）客户端。
 * 契约（手工定义，不走 contracts 生成类型——rest.d.ts 红线：不重生成，新增端点类型自持）：
 * - POST /ai/conversations/{cid}/steer  body {text, token}
 *   - 200 → SteerOut { run_id, accepted: true }：消息已进入活跃 run 的注入队列，
 *     在下一次工具调用结束后的模型请求前作为新用户输入注入当前轮次。
 *   - 409 → { detail: '当前没有进行中的任务' }：run 已结束/不存在，前端回退为常规发送。
 *   - 422 → text 为空/超 20000 字符、token 缺失（pydantic 校验）。
 * token 由前端生成（crypto.randomUUID），随 SteerAccepted SSE 事件回传用于对账。
 * SSE 事件侧（SteerAccepted）类型见 contracts/events.d.ts，由此处不复读。
 */
import { request } from './http'

/** steer 请求体。token 1-64 字符（后端 SteerBody 约束）。 */
export interface SteerBody {
  text: string
  token: string
}

/** steer 受理结果。accepted 恒为 true（非受理走 409）。 */
export interface SteerOut {
  run_id: string
  accepted: boolean
}

export function steerConversation(cid: number, body: SteerBody, signal?: AbortSignal): Promise<SteerOut> {
  // 不走 http.post：撤回需要 AbortSignal，直接用底层 request（fetch 的 signal 透传）
  return request<SteerOut>(`/ai/conversations/${cid}/steer`, { method: 'POST', body, signal })
}
