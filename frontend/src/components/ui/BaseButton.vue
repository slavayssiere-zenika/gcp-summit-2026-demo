<template>
  <button :class="['base-btn', variant]" :disabled="loading || disabled" @click="$emit('click')">
    <slot name="icon-left" />
    <span v-if="loading" class="spinner"></span>
    <span v-else><slot /></span>
    <slot name="icon-right" />
  </button>
</template>

<script setup lang="ts">
defineProps({
  variant: {
    type: String,
    default: 'primary' // 'primary', 'secondary', 'danger', 'ghost'
  },
  loading: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

defineEmits(['click'])
</script>

<style scoped>
.base-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-family: var(--font-family-base);
  font-size: 0.9rem;
  font-weight: 500;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  border: 1px solid transparent;
}

.base-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.primary {
  background: var(--zenika-red);
  color: var(--color-text-inverse);
}

.primary:hover:not(:disabled) {
  background: var(--zenika-red-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.secondary {
  background: var(--color-surface-base);
  color: var(--color-text-primary);
  border-color: #cbd5e0;
}

.secondary:hover:not(:disabled) {
  background: var(--color-surface-hover);
}

.danger {
  background: #ef4444;
  color: var(--color-text-inverse);
}

.danger:hover:not(:disabled) {
  background: #dc2626;
}

.ghost {
  background: transparent;
  color: var(--color-text-secondary);
}

.ghost:hover:not(:disabled) {
  background: rgba(0,0,0,0.05);
  color: var(--color-text-primary);
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 1s ease-in-out infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
