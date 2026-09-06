export {}
declare global {
  interface Window {
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
