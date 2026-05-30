<template>
  <div class="info-panel" :class="{ collapsed: isCollapsed }">
    <div class="info-header" @click="toggleCollapse">
      <div class="header-left">
        <UiIcon name="info" />
        <span class="info-title">系统信息</span>
      </div>
      <UiIcon name="arrow-right" class="toggle-icon" :class="{ rotated: !isCollapsed }" />
    </div>
    
    <div class="info-content" v-show="!isCollapsed">
      <div class="info-item">
        <span class="info-label">版本</span>
        <span class="info-value">v1.0.0</span>
      </div>
      <div class="info-item">
        <span class="info-label">Java</span>
        <span class="info-value" :class="{ 'status-error': !javaStatus }">
          {{ javaStatus ? '已就绪' : '未找到' }}
        </span>
      </div>
      <div class="info-item">
        <span class="info-label">内存</span>
        <span class="info-value">{{ memoryUsage }}</span>
      </div>
      <div class="info-item">
        <span class="info-label">状态</span>
        <span class="info-value status-online">
          <span class="status-dot"></span>
          在线
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const isCollapsed = ref(true)
const javaStatus = ref(true)
const memoryUsage = ref('0 MB')

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

// 模拟获取系统信息
const updateInfo = () => {
  // 模拟内存使用
  const used = Math.floor(Math.random() * 500) + 200
  memoryUsage.value = `${used} MB`
}

let timer: number

onMounted(() => {
  updateInfo()
  timer = window.setInterval(updateInfo, 5000)
})

onUnmounted(() => {
  clearInterval(timer)
})
</script>

<style scoped>
.info-panel {
  position: fixed;
  bottom: 20px;
  left: 84px;
  width: 200px;
  background: var(--bg-surface);
  backdrop-filter: blur(var(--blur-lg));
  -webkit-backdrop-filter: blur(var(--blur-lg));
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  transition: all 0.3s var(--ease-spring);
  z-index: 100;
  overflow: hidden;
}

/* 当侧边栏展开时调整位置 - 通过全局选择器适配 */
:global(.sidebar.expanded) ~ .main-content .info-panel {
  left: 260px;
}

.info-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s ease;
  border-bottom: 1px solid transparent;
}

.info-header:hover {
  background-color: var(--bg-surface-hover);
}

.info-header:active {
  background-color: var(--bg-surface-active);
}

.info-panel:not(.collapsed) .info-header {
  border-bottom-color: var(--divider-color);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon {
  font-size: 16px;
  color: var(--color-primary);
}

.info-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.toggle-icon {
  font-size: 12px;
  color: var(--text-secondary);
  transition: transform 0.3s var(--ease-spring);
}

.toggle-icon.rotated {
  transform: rotate(90deg);
}

.info-content {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.info-label {
  color: var(--text-secondary);
}

.info-value {
  color: var(--text-primary);
  font-weight: 500;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}

.status-online {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-success);
}

.status-dot {
  width: 6px;
  height: 6px;
  background-color: var(--color-success);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--color-success);
  animation: pulse 2s ease-in-out infinite;
}

.status-error {
  color: var(--color-error);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.info-panel.collapsed {
  box-shadow: var(--shadow-sm);
}

.info-panel.collapsed .info-header {
  border-bottom: none;
}

/* 暗色模式适配 */
[data-theme="dark"] .info-panel {
  background: rgba(45, 55, 75, 0.8);
}

/* 响应式适配 */
@media (max-height: 600px) {
  .info-panel {
    bottom: 10px;
    left: 74px;
    transform: scale(0.9);
    transform-origin: bottom left;
  }
}
</style>