/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// Tauri v2 + pytauri environment
interface Window {
  __TAURI__?: {
    core: {
      invoke: (cmd: string, args?: Record<string, unknown>) => Promise<any>
    }
  }
}

// i18n JSON imports
declare module '*.json' {
  const value: Record<string, any>
  export default value
}
