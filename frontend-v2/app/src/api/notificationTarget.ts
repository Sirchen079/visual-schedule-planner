import { parseCalendarTarget } from './calendarTarget'
import { followupTarget } from './followups'

/** Only routes implemented by the app may be opened from stored notification data. */
export function notificationTarget(value?: string | null, taskId?: number | null): string | undefined {
  if (value && /^\/board\?task=[1-9]\d*$/.test(value)) return value
  if (parseCalendarTarget(value)) return value!
  const bill = value?.match(/^\/ledger\?bill=([1-9]\d*)$/)
  if (bill && bill[0] === value && Number.isSafeInteger(Number(bill[1]))) return value!
  const project = value?.match(/^\/research\?project=([1-9]\d*)$/)
  if (project && project[0] === value && Number.isSafeInteger(Number(project[1]))) return value!
  const research = followupTarget(value)
  if (research) return research
  if (!value && Number.isSafeInteger(taskId) && taskId! > 0) return `/board?task=${taskId}`
  return undefined
}
