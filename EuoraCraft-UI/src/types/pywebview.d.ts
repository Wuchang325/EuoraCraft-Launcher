// src/types/pywebview.d.ts
// PyWebView API 类型声明

declare interface PyWebViewAPI {
  // 用户协议相关方法
  get_user_agreement_status: () => Promise<{ success: boolean; data?: { accepted: boolean }; message?: string }>
  save_user_agreement: () => Promise<{ success: boolean; message?: string }>
  clear_user_agreement: () => Promise<{ success: boolean; message?: string }>
  
  // 窗口控制方法
  minimize_window: () => void
  close_window: () => void
  
  // 文件和目录操作
  selectDirectory: () => Promise<{ success: boolean; data?: { path: string }; message?: string }>
  
  // 游戏配置相关
  getGameConfig: () => Promise<any>
  updateGameConfig: (config: any) => Promise<any>
  scanVersions: (paths: string[]) => Promise<any>
}

declare global {
  interface Window {
    pywebview?: {
      api: PyWebViewAPI
    }
  }
}

export {}