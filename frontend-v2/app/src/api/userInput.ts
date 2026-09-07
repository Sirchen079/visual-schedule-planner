export interface UserQuestion {
  id: string
  question: string
  options: Array<{ label: string; description: string }>
  multi_select: boolean
}
export interface UserAnswer { selected: string[]; text: string }
export interface UserInputRequest {
  id: number
  run_id: string
  call_id: string
  version: number
  status: 'pending' | 'answered' | 'skipped' | 'expired'
  questions: UserQuestion[]
  answer: { status?: string; answers?: Array<UserAnswer & { id: string; question: string }> }
  busy?: boolean
}
