<script setup lang="ts">
import { computed } from 'vue'
import { useUxStore } from '@/stores/uxStore'
import { CheckCircle, XCircle, Info, AlertTriangle, X } from 'lucide-vue-next'

const uxStore = useUxStore()

const toasts = computed(() => uxStore.toasts)

const iconMap = {
  success: CheckCircle,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
}
</script>

<template>
  <Teleport to="body">
    <div class="toast-container" aria-live="polite" aria-atomic="false">
      <TransitionGroup name="toast" tag="div" class="toast-wrapper">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="['toast', `toast--${toast.type}`]"
          role="alert"
          :aria-label="`Notification ${toast.type}: ${toast.message}`"
        >
          <component :is="iconMap[toast.type]" class="toast-icon" :size="18" />
          <span class="toast-message">{{ toast.message }}</span>
          <button
            class="toast-close"
            :aria-label="'Fermer la notification'"
            @click="uxStore.removeToast(toast.id)"
          >
            <X :size="14" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  pointer-events: none;
}

.toast-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.toast {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.85rem 1rem 0.85rem 1.1rem;
  border-radius: 12px;
  min-width: 280px;
  max-width: 420px;
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.14), 0 2px 8px rgba(0, 0, 0, 0.08);
  pointer-events: all;
  font-size: 0.875rem;
  font-weight: 500;
  line-height: 1.4;
  border: 1px solid transparent;
}

.toast--success {
  background: rgba(236, 253, 245, 0.95);
  color: #065f46;
  border-color: rgba(16, 185, 129, 0.25);
}

.toast--error {
  background: rgba(255, 241, 242, 0.97);
  color: #9b1c1c;
  border-color: rgba(227, 25, 55, 0.25);
}

.toast--info {
  background: rgba(239, 246, 255, 0.95);
  color: #1e40af;
  border-color: rgba(59, 130, 246, 0.25);
}

.toast--warning {
  background: rgba(255, 251, 235, 0.97);
  color: #92400e;
  border-color: rgba(245, 158, 11, 0.25);
}

.toast-icon {
  flex-shrink: 0;
}

.toast--success .toast-icon { color: #10b981; }
.toast--error   .toast-icon { color: #E31937; }
.toast--info    .toast-icon { color: #3b82f6; }
.toast--warning .toast-icon { color: #f59e0b; }

.toast-message {
  flex: 1;
}

.toast-close {
  flex-shrink: 0;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 2px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.55;
  transition: opacity 0.15s, background 0.15s;
  color: inherit;
}

.toast-close:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.07);
}

/* TransitionGroup animations */
.toast-enter-active {
  animation: toast-slide-in 0.28s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.toast-leave-active {
  animation: toast-slide-out 0.22s ease-in forwards;
}

.toast-move {
  transition: transform 0.25s ease;
}

@keyframes toast-slide-in {
  from {
    opacity: 0;
    transform: translateX(60px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}

@keyframes toast-slide-out {
  to {
    opacity: 0;
    transform: translateX(60px) scale(0.9);
  }
}
</style>
