<template>
  <div class="versions-container">
    <div ref="tabsRef" class="tabs-wrapper">
      <UiTabs v-model="activeTab" :items="tabs" />
    </div>

    <div class="versions-content" ref="contentRef">
      <ManageTab v-if="activeTab === 'manage'" class="tab-content" />
      <VersionsTab v-if="activeTab === 'versions'" class="tab-content" />
      <ModsTab v-if="activeTab === 'mods'" class="tab-content" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, defineAsyncComponent, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import gsap from 'gsap'
import '@/styles/views/Versions.css'
import UiTabs from '@/components/ui/Tabs.vue'

const ManageTab = defineAsyncComponent(() => import('./versions/ManageTab.vue'))
const VersionsTab = defineAsyncComponent(() => import('./versions/VersionsTab.vue'))
const ModsTab = defineAsyncComponent(() => import('./versions/ModsTab.vue'))

const { t } = useI18n()
const tabsRef = ref<HTMLElement | null>(null)
const contentRef = ref<HTMLElement | null>(null)
const activeTab = ref('manage')

const tabs = computed(() => [
  { id: 'manage', label: t('versions.manageTab'), icon: 'icon-settings' },
  { id: 'versions', label: t('versions.versions'), icon: 'icon-cube' },
  { id: 'mods', label: t('versions.modsTab'), icon: 'icon-cube' }
])

// 页面加载动画
const playEnterAnimation = () => {
  const tl = gsap.timeline()
  
  if (tabsRef.value) {
    tl.fromTo(tabsRef.value,
      { opacity: 0, y: -20, filter: 'blur(10px)' },
      { opacity: 1, y: 0, filter: 'blur(0px)', duration: 0.6, ease: 'power3.out' }
    )
  }

  if (contentRef.value) {
    tl.fromTo(contentRef.value,
      { opacity: 0, y: 20, scale: 0.98, filter: 'blur(10px)' },
      { opacity: 1, y: 0, scale: 1, filter: 'blur(0px)', duration: 0.6, ease: 'power3.out' },
      '-=0.4'
    )
  }
}

// 标签切换动画
const playSwitchAnimation = () => {
  if (!contentRef.value) return
  
  gsap.fromTo(contentRef.value,
    { opacity: 0, y: 10, scale: 0.98 },
    { opacity: 1, y: 0, scale: 1, duration: 0.4, ease: 'power2.out' }
  )
}

onMounted(() => {
  playEnterAnimation()
})

// 监听标签切换
watch(activeTab, () => {
  nextTick(() => {
    playSwitchAnimation()
  })
})
</script>
