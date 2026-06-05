/**
 * EuoraCraft Launcher - Tauri IPC API Client
 *
 * Replaces the old pywebview API bridge with Tauri invoke() calls.
 */

import { invoke } from '@tauri-apps/api/tauri'
import type {
  ApiResponse,
  LauncherConfig,
  BackgroundConfig,
  GameConfig,
  ThemeConfig,
  DownloadConfig,
  LocaleConfig,
  MouseEffectConfig,
  JavaInstallation,
  ScannedVersion,
  AccountInfo,
  GameInstance,
} from '@/types/api'

const DEBUG = import.meta.env.DEV

const logger = {
  log: (...args: any[]) => DEBUG && console.log('[API]', ...args),
  error: (...args: any[]) => console.error('[API Error]', ...args),
  warn: (...args: any[]) => console.warn('[API Warn]', ...args),
}

/**
 * Generic Tauri invoke wrapper.
 * Calls a backend command via IPC and returns a normalized ApiResponse.
 */
async function call<T = any>(command: string, args?: Record<string, unknown>): Promise<ApiResponse<T>> {
  try {
    logger.log(`invoke: ${command}`, args)
    const result = await invoke<ApiResponse<T>>(command, args)
    logger.log(`invoke result: ${command}`, result)
    return {
      success: result?.success ?? true,
      data: result?.data ?? (result as any),
      message: result?.message ?? '',
    }
  } catch (error) {
    logger.error(`invoke error: ${command}`, error)
    return {
      success: false,
      data: null as T,
      message: String(error),
    }
  }
}

/**
 * Ping the backend – useful for connection health checks.
 */
export async function ping(): Promise<ApiResponse<{ status: string; message: string }>> {
  return call('ping')
}

// ─── Config ──────────────────────────────────────────

export async function getLauncherConfig(): Promise<ApiResponse<LauncherConfig>> {
  return call('get_launcher_config')
}

export async function getGameConfig(): Promise<ApiResponse<GameConfig>> {
  return call('get_game_config')
}

export async function updateGameConfig(config: Partial<GameConfig>): Promise<ApiResponse<void>> {
  return call('update_game_config', { body: JSON.stringify(config) })
}

export async function getThemeConfig(): Promise<ApiResponse<ThemeConfig>> {
  return call('get_theme_config')
}

export async function updateThemeConfig(config: Partial<ThemeConfig>): Promise<ApiResponse<void>> {
  return call('update_theme_config', { body: JSON.stringify(config) })
}

export async function getBackgroundConfig(): Promise<ApiResponse<BackgroundConfig>> {
  return call('get_background_config')
}

export async function updateBackgroundConfig(config: Partial<BackgroundConfig>): Promise<ApiResponse<void>> {
  return call('update_background_config', { body: JSON.stringify(config) })
}

export async function getDownloadConfig(): Promise<ApiResponse<DownloadConfig>> {
  return call('get_download_config')
}

export async function updateDownloadConfig(config: Partial<DownloadConfig>): Promise<ApiResponse<void>> {
  return call('update_download_config', { body: JSON.stringify(config) })
}

export async function getLocaleConfig(): Promise<ApiResponse<LocaleConfig>> {
  return call('get_locale_config')
}

export async function updateLocaleConfig(locale: string): Promise<ApiResponse<void>> {
  return call('update_locale_config', { body: JSON.stringify({ locale }) })
}

export async function getMouseEffectConfig(): Promise<ApiResponse<MouseEffectConfig>> {
  return call('get_mouse_effect_config')
}

export async function updateMouseEffectConfig(config: Partial<MouseEffectConfig>): Promise<ApiResponse<void>> {
  return call('update_mouse_effect_config', { body: JSON.stringify(config) })
}

// ─── Background Image ────────────────────────────────

export async function getBackgroundImage(): Promise<ApiResponse<{ base64: string; path: string; type: string }>> {
  return call('get_background_image')
}

// ─── Java ────────────────────────────────────────────

export async function getJavaList(): Promise<ApiResponse<JavaInstallation[]>> {
  return call('get_java_list')
}

// ─── Version Scanning ────────────────────────────────

export async function scanVersions(_paths: string[]): Promise<ApiResponse<ScannedVersion[]>> {
  return call('scan_versions_in_path', { body: JSON.stringify({ paths: _paths }) })
}

export async function selectLocalImage(): Promise<ApiResponse<{ path: string }>> {
  return call('select_local_image')
}

export async function selectDirectory(): Promise<ApiResponse<{ path: string }>> {
  return call('select_directory')
}

export async function selectJavaExecutable(): Promise<ApiResponse<{ path: string }>> {
  return call('select_java_executable')
}

export async function getMinecraftVersions(): Promise<ApiResponse<any>> {
  return call('get_minecraft_versions')
}

export async function getFabricVersions(gameVersionId?: string): Promise<ApiResponse<string[]>> {
  return call('get_fabric_versions', { body: JSON.stringify({ gameVersionId }) })
}

export async function launchInstance(params: {
  version: string
  gamePath?: string
  javaPath?: string
  maxMemory?: number
  playerName?: string
}): Promise<ApiResponse<{ taskId?: string }>> {
  return call('launch_instance', { body: JSON.stringify(params) })
}

export async function getLaunchStatus(taskId: string): Promise<ApiResponse<{ completed: boolean; percent: number; stage: string; message: string; error?: string }>> {
  return call('get_launch_status', { body: JSON.stringify({ taskId }) })
}

export async function uninstallVersion(version: string, gamePath?: string): Promise<ApiResponse<void>> {
  return call('uninstall_version', { body: JSON.stringify({ version, gamePath }) })
}

// ─── Game Launch ─────────────────────────────────────

export async function launchGame(params: {
  versionId: string
  javaPath?: string
  maxMemory?: number
  playerName?: string
}): Promise<ApiResponse<void>> {
  return call('launch_game', { body: JSON.stringify(params) })
}

// ─── Accounts ────────────────────────────────────────

export async function getAccounts(): Promise<ApiResponse<{ accounts: AccountInfo[]; current: AccountInfo | null }>> {
  return call('get_accounts')
}

export async function getCurrentAccount(): Promise<ApiResponse<AccountInfo | null>> {
  return call('get_current_account')
}

export async function addOfflineAccount(username: string): Promise<ApiResponse<any>> {
  return call('add_offline_account', { body: JSON.stringify({ username }) })
}

export async function startMicrosoftLogin(): Promise<ApiResponse<any>> {
  return call('start_microsoft_login')
}

export async function pollMicrosoftLogin(): Promise<ApiResponse<{ status: string; message: string; retry_after?: number }>> {
  return call('poll_microsoft_login')
}

export async function completeMicrosoftLogin(): Promise<ApiResponse<any>> {
  return call('complete_microsoft_login')
}

export async function switchAccount(accountId: string): Promise<ApiResponse<any>> {
  return call('switch_account', { body: JSON.stringify({ accountId }) })
}

export async function removeAccount(accountId: string): Promise<ApiResponse<any>> {
  return call('remove_account', { body: JSON.stringify({ accountId }) })
}

// ─── User Agreement ──────────────────────────────────

export async function getUserAgreementStatus(): Promise<ApiResponse<{ accepted: boolean; uuid: string }>> {
  return call('get_user_agreement_status')
}

export async function saveUserAgreement(): Promise<ApiResponse<{ accepted: boolean; uuid: string }>> {
  return call('save_user_agreement')
}

// ─── Windows Controls ────────────────────────────────

export async function minimizeWindow(): Promise<void> {
  await invoke('minimize_window')
}

export async function closeWindow(): Promise<void> {
  await invoke('close_window')
}

export async function toggleMaximize(): Promise<void> {
  await invoke('toggle_maximize')
}

// ─── Instances ────────────────────────────────────────

export async function getGameInstances(): Promise<ApiResponse<GameInstance[]>> {
  return call('get_game_instances')
}

export async function stopInstance(instanceId: string): Promise<ApiResponse<void>> {
  return call('stop_instance', { body: JSON.stringify({ instanceId }) })
}

// ─── Background Image Upload ─────────────────────────

export async function updateBackgroundImage(type: string, path: string): Promise<ApiResponse<void>> {
  return call('update_background_image', { body: JSON.stringify({ type, path }) })
}

export async function loadImageFromUrl(url: string): Promise<ApiResponse<{ path: string }>> {
  return call('load_image_from_url', { body: JSON.stringify({ url }) })
}

// ─── Singleton export ────────────────────────────────

export const api = {
  // Config
  getLauncherConfig,
  getGameConfig,
  updateGameConfig,
  getThemeConfig,
  updateThemeConfig,
  getBackgroundConfig,
  updateBackgroundConfig,
  getDownloadConfig,
  updateDownloadConfig,
  getLocaleConfig,
  updateLocaleConfig,
  getMouseEffectConfig,
  updateMouseEffectConfig,

  // Background
  getBackgroundImage,

  // Java
  getJavaList,

  // Version
  scanVersions,
  selectLocalImage,
  selectDirectory,
  selectJavaExecutable,
  getMinecraftVersions,
  getFabricVersions,
  launchInstance,
  getLaunchStatus,
  uninstallVersion,

  // Launch
  launchGame,

  // Accounts
  getAccounts,
  getCurrentAccount,
  addOfflineAccount,
  startMicrosoftLogin,
  pollMicrosoftLogin,
  completeMicrosoftLogin,
  switchAccount,
  removeAccount,

  // Instances
  getGameInstances,
  stopInstance,

  // Background Image Upload
  updateBackgroundImage,
  loadImageFromUrl,

  // Agreement
  getUserAgreementStatus,
  saveUserAgreement,

  // Window
  minimizeWindow,
  closeWindow,
  toggleMaximize,

  // Health
  ping,
}
