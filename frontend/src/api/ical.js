// iCal 导入导出 API 封装。导出直接浏览器下载（Content-Disposition attachment）；
// 导入走 multipart 上传，字段名 file，失败时取后端 detail 作为错误信息。

export function exportTasksUrl() {
  return '/export/tasks.ics'
}

export function importTasksIcs(file) {
  const form = new FormData()
  form.append('file', file)
  return fetch('/import/tasks.ics', { method: 'POST', body: form }).then(async (res) => {
    if (!res.ok) {
      let detail = `请求失败 (${res.status})`
      try {
        const data = await res.json()
        if (data?.detail) detail = data.detail
      } catch {
        // 非 JSON 错误体时沿用状态码提示
      }
      throw new Error(detail)
    }
    return res.json()
  })
}
