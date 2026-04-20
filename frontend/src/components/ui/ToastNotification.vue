<template>
  <div class="toast-container">
    <transition-group name="toast">
      <div v-for="toast in uxStore.toasts" :key="toast.id" :class="['toast', toast.type]">
        <CheckCircle v-if="toast.type === 'success'" size="18" />
        <AlertCircle v-else-if="toast.type === 'error'" size="18" />
        <AlertTriangle v-else-if="toast.type === 'warning'" size="18" />
        <Info v-else size="18" />
        <span>{{ toast.message }}</span>
        <button @click="uxStore.removeToast(toast.id)" class="close-btn"><X size="14" /></button>
      </div>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import { CheckCircle, AlertCircle, AlertTriangle, Info, X } from 'lucide-vue-next'
import { useUxStore } from '@/stores/uxStore'

const uxStore = useUxStore()
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-glass);
  background: white;
  color: var(--color-text-primary);
  font-size: 0.85rem;
  font-weight: 500;
  pointer-events: auto;
  min-width: 250px;
}

.toast.success { border-left: 4px solid #10b981; }
.toast.success svg { color: #10b981; }

.toast.error { border-left: 4px solid #ef4444; }
.toast.error svg { color: #ef4444; }

.toast.info { border-left: 4px solid #3b82f6; }
.toast.info svg { color: #3b82f6; }

.toast.warning { border-left: 4px solid #f59e0b; background: #fffbeb; }
.toast.warning svg { color: #d97706; }

.close-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  margin-left: auto;
  color: var(--color-text-secondary);
}

.close-btn:hover {
  color: var(--color-text-primary);
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(30px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(30px);
}
</style>
