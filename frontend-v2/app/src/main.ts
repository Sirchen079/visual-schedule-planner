import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import WidgetApp from './WidgetApp.vue'
import router from './router'
import { useSettingsStore } from './stores/settings'
import { applyTheme, readLocalTheme } from './utils/theme'
import './tokens.css'

// 主题首帧引导：必须在挂载前落到 documentElement 上，否则首帧会闪色。
// localStorage 只是本 origin 的首帧缓存；跨端口权威源是后端 ui.theme（re #065，
// re gpt6astra #063 major：壳每次随机端口，localStorage 按 origin 隔离），
// 挂载后由 reconcileTheme 异步调和，远端不同步才重刷，失败静默不阻塞首屏。
applyTheme(readLocalTheme())

// 注：不能用 router.isReady() 再挂载——初始导航在 app.use(router) 时才启动，
// 不挂载 isReady 永不 resolve。首帧 route 未就绪的容错由 App.vue 的 headTitle 处理。
const widgetMode = new URLSearchParams(location.search).get('widget') === '1'
if (widgetMode) document.documentElement.classList.add('widget-mode')
createApp(widgetMode ? WidgetApp : App).use(createPinia()).use(router).mount('#app')

void useSettingsStore().reconcileTheme()
