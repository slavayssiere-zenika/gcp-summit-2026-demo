import { defineStore } from 'pinia'

export const ONBOARDING_KEY = 'zenika_onboarding_done'

export interface OnboardingStep {
  title: string
  body: string
  /** Sélecteur CSS de l'élément à mettre en évidence */
  selector: string
}

/** Sélecteurs CSS des éléments ciblés par le tour (ordre = étapes) */
export const STEP_SELECTORS: string[] = [
  '.welcome-section',
  '.input-container textarea',
  '.tab-btn:last-of-type',
  '.finops-badge',
  '.reset-history-btn',
]

/** Nombre total d'étapes du tour */
export const TOTAL_STEPS = STEP_SELECTORS.length

export const useOnboardingStore = defineStore('onboarding', {
  state: () => ({
    isActive: false,
    currentStep: 0,
    isDone: localStorage.getItem(ONBOARDING_KEY) === 'true',
  }),

  getters: {
    isLastStep: (s) => s.currentStep >= TOTAL_STEPS - 1,
    totalSteps: () => TOTAL_STEPS,
  },

  actions: {
    start() {
      this.currentStep = 0
      this.isActive = true
    },

    next() {
      if (this.isLastStep) {
        this.complete()
      } else {
        this.currentStep++
      }
    },

    skip() {
      this.complete()
    },

    complete() {
      this.isActive = false
      this.isDone = true
      localStorage.setItem(ONBOARDING_KEY, 'true')
    },

    /**
     * Relance le tour depuis le début, quel que soit l'état isDone.
     * Utilisé par le bouton "?" de la navbar.
     */
    restart() {
      this.currentStep = 0
      this.isActive = true
    },
  },
})
