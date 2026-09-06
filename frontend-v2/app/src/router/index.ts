import { createRouter, createWebHashHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import TodayView from '../views/TodayView.vue'
import CalendarView from '../views/CalendarView.vue'
import BoardView from '../views/BoardView.vue'
import TimelineView from '../views/TimelineView.vue'
import HabitsView from '../views/HabitsView.vue'
import JournalView from '../views/JournalView.vue'
import GoalsView from '../views/GoalsView.vue'
import LibraryView from '../views/LibraryView.vue'
import TrashView from '../views/TrashView.vue'
import SettingsView from '../views/SettingsView.vue'
import ReportsView from '../views/ReportsView.vue'
import LedgerView from '../views/LedgerView.vue'
import InboxView from '../views/InboxView.vue'
import ResearchView from '../views/ResearchView.vue'

/** 导航扩展元信息：title 页面名；group 区分主/次导航。 */
export interface NavMeta {
  title: string
  group: 'main' | 'aux'
}

/**
 * M3：七大域视图全部落地（看板/时间轴/习惯/日记/目标/资料库/回收站），
 * M4a：设置页落地（自治档位/永久授权/MCP 清单），M4b：报表页落地（列表/纸面详情/手动生成），占位视图清空。
 * 用 hash 模式——本地桌面单机应用最稳
 * （后端 SPA 托管支持 history 模式，后续如需可切）。
 */
export const routes: RouteRecordRaw[] = [
  { path: '/research', name: 'research', component: ResearchView, meta: { title: '学习与研究', group: 'main' } },
  { path: '/', name: 'today', component: TodayView, meta: { title: '今日', group: 'main' } },
  { path: '/inbox', name: 'inbox', component: InboxView, meta: { title: '收件箱', group: 'main' } },
  { path: '/calendar', name: 'calendar', component: CalendarView, meta: { title: '日历', group: 'main' } },
  { path: '/board', name: 'board', component: BoardView, meta: { title: '看板', group: 'main' } },
  { path: '/timeline', name: 'timeline', component: TimelineView, meta: { title: '时间轴', group: 'main' } },
  { path: '/habits', name: 'habits', component: HabitsView, meta: { title: '习惯', group: 'main' } },
  { path: '/journal', name: 'journal', component: JournalView, meta: { title: '日记', group: 'main' } },
  { path: '/ledger', name: 'ledger', component: LedgerView, meta: { title: '账本', group: 'main' } },
  { path: '/goals', name: 'goals', component: GoalsView, meta: { title: '目标', group: 'main' } },
  { path: '/library', name: 'library', component: LibraryView, meta: { title: '资料库', group: 'main' } },
  { path: '/reports', name: 'reports', component: ReportsView, meta: { title: '日报周报', group: 'aux' } },
  { path: '/trash', name: 'trash', component: TrashView, meta: { title: '回收站', group: 'aux' } },
  { path: '/settings', name: 'settings', component: SettingsView, meta: { title: '设置', group: 'aux' } },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.afterEach((to) => {
  const meta = to.meta as unknown as NavMeta
  document.title = meta.title ? `${meta.title} · 知时` : '知时'
})

export default router
