import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useConversationStore } from './conversation'
import { useRunStore } from './run'
import { buildTimeline } from '../components/chat/timeline'

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const message = (id: number, text: string, run_id?: string) => ({ id, role: 'user', display: { text, run_id }, created_at:'2026-01-01T10:00:00' })
function pending<T>() { let resolve!: (v:T)=>void; const promise = new Promise<T>(r => {resolve=r}); return { promise, resolve } }
function stream(cid:number) { return new Response([{type:'run_started',run_id:'accepted',conversation_id:cid,v:1},{type:'done',run_id:'accepted',v:1}].map(e=>`data: ${JSON.stringify(e)}\n\n`).join(''), {headers:{'Content-Type':'text/event-stream'}}) }
beforeEach(() => setActivePinia(createPinia()))
afterEach(() => { useRunStore().reset(null); vi.unstubAllGlobals() })

describe('durable sessions and late asynchronous responses', () => {
  it('a failed selection retains the old conversation and its draft', async () => {
    const conv = useConversationStore()
    conv.activeId = 1; conv.messages = [message(1,'A原文')]; conv.draftText='A草稿'
    vi.stubGlobal('fetch', vi.fn(async () => json({detail:'暂时离线'},503)))
    await conv.select(2)
    expect(conv.activeId).toBe(1)
    expect(conv.messages[0]?.display.text).toBe('A原文')
    expect(conv.draftText).toBe('A草稿')
    expect(conv.error).toContain('暂时离线')
  })
  it('switches drafts with their own attachments and keeps them after failed send', async () => {
    const conv = useConversationStore()
    conv.activeId=1; conv.draftText='A草稿'; conv.draftAttachments=[{id:7,name:'A.txt'}]
    vi.stubGlobal('fetch',vi.fn(async () => json([])))
    await conv.select(2)
    expect(conv.draftText).toBe(''); expect(conv.draftAttachments).toEqual([])
    conv.draftText='B草稿'
    await conv.select(1)
    expect(conv.draftText).toBe('A草稿'); expect(conv.attachmentIds).toEqual([7])
    vi.stubGlobal('fetch',vi.fn(async () => json({detail:'加载失败'},500)))
    await conv.sendMessage('A草稿',{attachmentIds:[7]})
    expect(conv.draftText).toBe('A草稿'); expect(conv.attachmentIds).toEqual([7])
    expect(useRunStore().sentMessage).toBeNull()
  })
  it('clears the draft only after acceptance and preserves text edited while connecting', async () => {
    const conv = useConversationStore(), accepted = pending<Response>()
    conv.draftText='原始输入'; conv.draftAttachments=[{id:7,name:'原附件'}]
    vi.stubGlobal('fetch',vi.fn((url:string) => url==='/ai/chat/stream' ? accepted.promise : Promise.resolve(json([]))))
    const sending = conv.sendMessage('原始输入',{attachmentIds:[7]})
    expect(conv.draftText).toBe('原始输入'); expect(conv.attachmentIds).toEqual([7])
    conv.draftText='修改后的下一条输入'
    accepted.resolve(stream(9)); await sending
    expect(conv.activeId).toBe(9)
    expect(conv.draftText).toBe('修改后的下一条输入')
    expect(conv.attachmentIds).toEqual([])
  })
  it('late approval cannot resume or mark a different conversation', async () => {
    const run = useRunStore(), response = pending<Response>()
    run.conversationId=1; run.runId='r1'; run.phase='awaiting_approval'
    run.approvalLedger=[{actionId:1,tool:'delete_task',args:{},preview:'A',grantAvailable:false,outcome:null}]
    const fetch = vi.fn(() => response.promise); vi.stubGlobal('fetch',fetch)
    const approving = run.approve(1)
    run.reset(2); run.runId='r2'; run.notice='B仍在当前视图'
    response.resolve(json({ok:true,ready_to_resume:true,resume:'/ai/conversations/1/resume/stream'}))
    await approving
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(run.conversationId).toBe(2); expect(run.notice).toBe('B仍在当前视图')
    expect(run.error).toBeNull()
  })
  it('late rejection does not clear a different conversation plan with the same numeric id', async () => {
    const run=useRunStore(), response=pending<Response>()
    run.conversationId=1; run.planCard={planId:1,title:'A计划',steps:[]}
    vi.stubGlobal('fetch',vi.fn(() => response.promise))
    const rejecting=run.rejectPlan()
    run.reset(2); run.planCard={planId:1,title:'B计划',steps:[]}
    response.resolve(json({ok:true})); await rejecting
    expect(run.planCard?.title).toBe('B计划')
  })
  it('serializes workspace saves so a late older write cannot overwrite a newer draft', async () => {
    const conv=useConversationStore(), first=pending<Response>(), bodies:any[]=[]
    conv.initialized=true
    vi.stubGlobal('fetch',vi.fn((_url:string,init:RequestInit) => {
      const body=JSON.parse(String(init.body)); bodies.push(body)
      return bodies.length===1 ? first.promise : Promise.resolve(json({...body,revision:body.revision+1}))
    }))
    conv.draftText='第一版'; conv.saveDraft()
    conv.draftText='第二版'; conv.saveDraft()
    expect(bodies).toHaveLength(1)
    first.resolve(json({...bodies[0],revision:1}))
    await vi.waitFor(()=>expect(conv.savingWorkspace).toBe(false))
    expect(bodies).toHaveLength(2)
    expect(bodies[1].revision).toBe(1)
    expect(bodies[1].state.drafts.new.text).toBe('第二版')
  })
  it('deduplicates a persisted in-progress checkpoint against the matching live run', () => {
    const run=useRunStore(); run.conversationId=1; run.runId='r1'; run.sentMessage='输入'
    run.segments=[{kind:'text',content:'部分回复',seq:1}]
    const history=[message(1,'输入','r1'),{...message(2,'部分回复','r1'),role:'assistant'}]
    expect(buildTimeline({messages:history,run,activeConversationId:1}).map(i=>i.kind)).toEqual(['sent','text'])
    expect(buildTimeline({messages:history,run,activeConversationId:2}).map(i=>i.kind)).toEqual(['history-user','history-assistant'])
  })
})
