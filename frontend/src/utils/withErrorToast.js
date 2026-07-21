// 统一错误提示包装：给弹窗内的轻量异步操作（附件、子任务等）补「失败提示」。
// 用法：await withErrorToast(toast, '关联资料失败', async () => { ... })
// 默认吞掉异常（表单态保持原样，调用点无需感知）；
// 调用点需要继续处理异常时传 { rethrow: true } 重新抛出。
export async function withErrorToast(toast, failMessage, fn, { rethrow = false } = {}) {
  try {
    return await fn()
  } catch (e) {
    toast?.error?.(`${failMessage}：${e?.message || '未知错误'}`)
    if (rethrow) throw e
    return undefined
  }
}
