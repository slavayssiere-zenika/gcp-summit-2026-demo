<script setup lang="ts">
import { ref, watch, nextTick, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOnboardingStore, STEP_SELECTORS, TOTAL_STEPS, type OnboardingStep } from '@/stores/onboardingStore'
import OnboardingStepView from './OnboardingStep.vue'

const store = useOnboardingStore()
const { t } = useI18n()

/** Étapes résolues via i18n — réactives à la locale */
const STEPS = computed<OnboardingStep[]>(() => [
  { title: t('onboarding.step1_title'), body: t('onboarding.step1_body'), selector: STEP_SELECTORS[0] },
  { title: t('onboarding.step2_title'), body: t('onboarding.step2_body'), selector: STEP_SELECTORS[1] },
  { title: t('onboarding.step3_title'), body: t('onboarding.step3_body'), selector: STEP_SELECTORS[2] },
  { title: t('onboarding.step4_title'), body: t('onboarding.step4_body'), selector: STEP_SELECTORS[3] },
  { title: t('onboarding.step5_title'), body: t('onboarding.step5_body'), selector: STEP_SELECTORS[4] },
])

const currentStepData = computed(() => STEPS.value[store.currentStep])

// Spotlight rect de l'élément ciblé
const spotlightRect = ref<DOMRect | null>(null)
const tooltipPosition = ref<'top' | 'bottom'>('bottom')
const tooltipStyle = ref<Record<string, string>>({})

const PADDING = 8

function applySpotlight() {
  const selector = STEP_SELECTORS[store.currentStep]
  const el = document.querySelector(selector)
  if (!el) {
    spotlightRect.value = null
    tooltipPosition.value = 'bottom'
    tooltipStyle.value = { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
    return
  }

  const rect = el.getBoundingClientRect()
  spotlightRect.value = rect

  const viewportH = window.innerHeight
  const spaceBelow = viewportH - rect.bottom

  if (spaceBelow >= 180 || spaceBelow >= rect.top) {
    tooltipPosition.value = 'bottom'
    tooltipStyle.value = {
      top: `${rect.bottom + PADDING + 8}px`,
      left: `${Math.min(rect.left, window.innerWidth - 340)}px`,
    }
  } else {
    tooltipPosition.value = 'top'
    tooltipStyle.value = {
      bottom: `${viewportH - rect.top + PADDING + 8}px`,
      left: `${Math.min(rect.left, window.innerWidth - 340)}px`,
    }
  }
}

watch(
  () => [store.isActive, store.currentStep],
  ([isActive]) => {
    if (isActive) {
      nextTick(applySpotlight)
    } else {
      spotlightRect.value = null
    }
  },
  { immediate: true }
)

function onResize() {
  if (store.isActive) applySpotlight()
}
window.addEventListener('resize', onResize)
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<template>
  <Teleport to="body">
    <Transition name="onboarding-fade">
      <div
        v-if="store.isActive"
        class="onboarding-overlay"
        @click.self="store.skip()"
        role="presentation"
        aria-hidden="true"
      >
        <!-- Spotlight autour de l'élément ciblé -->
        <div
          v-if="spotlightRect"
          class="onboarding-spotlight"
          :style="{
            left: `${spotlightRect.left - PADDING}px`,
            top: `${spotlightRect.top - PADDING}px`,
            width: `${spotlightRect.width + PADDING * 2}px`,
            height: `${spotlightRect.height + PADDING * 2}px`,
          }"
        />

        <!-- Bulle tooltip positionnée -->
        <div class="onboarding-bubble-wrapper" :style="tooltipStyle">
          <OnboardingStepView
            :step="currentStepData"
            :current="store.currentStep + 1"
            :total="TOTAL_STEPS"
            :position="tooltipPosition"
            @next="store.next()"
            @skip="store.skip()"
          />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.onboarding-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(1.5px);
}

.onboarding-spotlight {
  position: absolute;
  border-radius: 10px;
  box-shadow: 0 0 0 4px rgba(227, 25, 55, 0.5);
  background: transparent;
  pointer-events: none;
  animation: spotlightPulse 2s ease-in-out infinite;
}

@keyframes spotlightPulse {
  0%, 100% { box-shadow: 0 0 0 4px rgba(227, 25, 55, 0.5); }
  50%       { box-shadow: 0 0 0 6px rgba(227, 25, 55, 0.25); }
}

.onboarding-bubble-wrapper {
  position: fixed;
  z-index: 10001;
  pointer-events: all;
}

.onboarding-fade-enter-active,
.onboarding-fade-leave-active {
  transition: opacity 0.25s ease;
}

.onboarding-fade-enter-from,
.onboarding-fade-leave-to {
  opacity: 0;
}
</style>
