/**
 * User Agreement composable – now uses Tauri IPC via the api module.
 */
import { ref, readonly } from 'vue'
import { api } from '@/api/client'

const isAccepted = ref(false)
const isLoading = ref(true)
const agreementUrl = 'https://github.com/ECLTeam/EuoraCraft-Launcher/blob/main/LICENSE'

async function checkUserAgreement(): Promise<boolean> {
  try {
    const result = await api.getUserAgreementStatus()
    if (result.success && result.data?.accepted) {
      isAccepted.value = true
      return true
    }
    return false
  } catch (e) {
    console.error('[UserAgreement] check failed:', e)
    return false
  } finally {
    isLoading.value = false
  }
}

async function acceptUserAgreement(): Promise<boolean> {
  try {
    const result = await api.saveUserAgreement()
    if (result.success) {
      isAccepted.value = true
      return true
    }
    return false
  } catch (e) {
    console.error('[UserAgreement] accept failed:', e)
    return false
  }
}

function useUserAgreement() {
  return {
    isAccepted: readonly(isAccepted),
    isLoading: readonly(isLoading),
    agreementUrl,
    checkUserAgreement,
    acceptUserAgreement,
  }
}

export { useUserAgreement, checkUserAgreement, acceptUserAgreement }
