<script setup lang="ts">
import { computed } from 'vue'
import type { OnboardingStep } from '@/stores/onboardingStore'
import { X } from 'lucide-vue-next'

const props = defineProps<{
  step: OnboardingStep
  current: number
  total: number
  /** 'top' | 'bottom' — calculé par OnboardingTour selon la position de l'élément ciblé */
  position?: 'top' | 'bottom'
}>()

const emit = defineEmits<{
  next: []
  skip: []
}>()

const isLast = computed(() => props.current >= props.total)
</script>

<template>
  <div class="onboarding-bubble" :class="`placement-${position ?? 'bottom'}`" role="dialog" aria-modal="true" :aria-label="`Étape ${current} sur ${total} : ${step.title}`">
    <!-- Close button -->
    <button class="ob-close" @click="emit('skip')" aria-label="Fermer le tour guidé">
      <X size="14" />
    </button>

    <!-- Content -->
    <div class="ob-header">
      <span class="ob-title">{{ step.title }}</span>
      <span class="ob-progress">{{ current }}/{{ total }}</span>
    </div>
    <p class="ob-body">{{ step.body }}</p>

    <!-- Arrow pointer -->
    <div class="ob-arrow" />

    <!-- Footer -->
    <div class="ob-footer">
      <button class="ob-skip" @click="emit('skip')">Ignorer le tour</button>
      <button class="ob-next" @click="emit('next')">
        {{ isLast ? 'Terminer ✓' : 'Suivant →' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.onboarding-bubble {
  position: fixed;
  z-index: 10001;
  background: white;
  border-radius: 16px;
  padding: 1.25rem 1.5rem 1rem;
  width: 320px;
  box-shadow:
    0 20px 60px rgba(0, 0, 0, 0.18),
    0 4px 20px rgba(227, 25, 55, 0.12);
  border: 1.5px solid rgba(227, 25, 55, 0.15);
  animation: bubbleIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  pointer-events: all;
}

@keyframes bubbleIn {
  from { opacity: 0; transform: scale(0.92) translateY(6px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}

/* Arrow pointer */
.ob-arrow {
  position: absolute;
  width: 12px;
  height: 12px;
  background: white;
  border: 1.5px solid rgba(227, 25, 55, 0.15);
  transform: rotate(45deg);
}

.placement-bottom .ob-arrow {
  top: -7px;
  left: 24px;
  border-right: none;
  border-bottom: none;
}

.placement-top .ob-arrow {
  bottom: -7px;
  left: 24px;
  border-left: none;
  border-top: none;
}

/* Header */
.ob-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.6rem;
}

.ob-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.4;
}

.ob-progress {
  font-size: 0.72rem;
  font-weight: 600;
  color: #94a3b8;
  background: #f1f5f9;
  padding: 0.2rem 0.5rem;
  border-radius: 20px;
  white-space: nowrap;
  flex-shrink: 0;
  margin-left: 0.75rem;
}

/* Body */
.ob-body {
  font-size: 0.875rem;
  color: #475569;
  line-height: 1.6;
  margin-bottom: 1rem;
}

/* Close */
.ob-close {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  background: #f1f5f9;
  border: none;
  border-radius: 6px;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #94a3b8;
  transition: all 0.15s;
}

.ob-close:hover {
  background: #fee2e2;
  color: #dc2626;
}

/* Footer */
.ob-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid #f1f5f9;
  padding-top: 0.75rem;
}

.ob-skip {
  background: none;
  border: none;
  font-size: 0.78rem;
  color: #94a3b8;
  cursor: pointer;
  padding: 0.25rem;
  transition: color 0.15s;
}

.ob-skip:hover {
  color: #64748b;
  text-decoration: underline;
}

.ob-next {
  background: var(--zenika-red, #e31937);
  color: white;
  border: none;
  padding: 0.45rem 1.1rem;
  border-radius: 10px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.25);
}

.ob-next:hover {
  background: #c41230;
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(227, 25, 55, 0.35);
}
</style>
