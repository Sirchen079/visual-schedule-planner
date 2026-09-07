import type { UpdateState } from './stores/updates'
export {}
declare global {
  interface Window {
    zhishiUpdates?: {
      state: () => Promise<UpdateState>
      check: () => Promise<UpdateState>
      downloadAndInstall: () => Promise<UpdateState>
      install: () => Promise<UpdateState>
      openReleases: () => Promise<void>
      onChanged: (callback: (state: UpdateState) => void) => () => void
      onPrepare: (callback: () => Promise<void>) => () => void
    }
    zhishiWidget?: {
      state: () => Promise<{ pinned: boolean; collapsed: boolean }>
      control: (action: 'pin' | 'collapse' | 'hide' | 'main') => Promise<{ pinned: boolean; collapsed: boolean }>
      openMain: (path: string) => Promise<{ pinned: boolean; collapsed: boolean }>
      onStateChanged?: (callback: (state: { pinned: boolean; collapsed: boolean }) => void) => () => void
    }
    zhishiDesktop?: {
      preferences: () => Promise<DesktopPreferences>
      updatePreferences: (patch: Partial<Record<'visible' | 'pinned' | 'collapsed' | 'resetPosition' | 'notifications', boolean>>) => Promise<DesktopPreferences>
      onPreferencesChanged: (callback: (state: DesktopPreferences) => void) => () => void
    }
  }
  interface DesktopPreferences {
    visible: boolean
    pinned: boolean
    collapsed: boolean
    notifications: boolean
    shortcutRegistered: boolean
  }
}
