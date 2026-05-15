import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useOnboardingStore, ONBOARDING_KEY, STEP_SELECTORS, TOTAL_STEPS } from '@/stores/onboardingStore'

// Simule un localStorage complet compatible jsdom (contourne le bug --localstorage-file)
function makeFakeStorage() {
  const store: Record<string, string> = {}
  return {
    _store: store,
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, val: string) => { store[key] = val },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() { return Object.keys(store).length },
  }
}

describe('onboardingStore', () => {
  let fakeStorage: ReturnType<typeof makeFakeStorage>

  beforeEach(() => {
    fakeStorage = makeFakeStorage()
    vi.stubGlobal('localStorage', fakeStorage)
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('isDone est false si localStorage vide', () => {
    const store = useOnboardingStore()
    expect(store.isDone).toBe(false)
  })

  it('isDone est true si localStorage contient la clé', () => {
    localStorage.setItem(ONBOARDING_KEY, 'true')
    const store = useOnboardingStore()
    expect(store.isDone).toBe(true)
  })

  it('start() active le tour et reset le step à 0', () => {
    const store = useOnboardingStore()
    store.currentStep = 3
    store.start()
    expect(store.isActive).toBe(true)
    expect(store.currentStep).toBe(0)
  })

  it('next() avance l\'étape', () => {
    const store = useOnboardingStore()
    store.start()
    store.next()
    expect(store.currentStep).toBe(1)
  })

  it('next() sur la dernière étape appelle complete()', () => {
    const store = useOnboardingStore()
    store.start()
    store.currentStep = TOTAL_STEPS - 1

    store.next()

    expect(store.isActive).toBe(false)
    expect(store.isDone).toBe(true)
    expect(localStorage.getItem(ONBOARDING_KEY)).toBe('true')
  })

  it('skip() ferme le tour et marque done en localStorage', () => {
    const store = useOnboardingStore()
    store.start()
    store.skip()

    expect(store.isActive).toBe(false)
    expect(store.isDone).toBe(true)
    expect(localStorage.getItem(ONBOARDING_KEY)).toBe('true')
  })

  it('complete() persiste isDone=true en localStorage', () => {
    const store = useOnboardingStore()
    store.complete()

    expect(store.isDone).toBe(true)
    expect(localStorage.getItem(ONBOARDING_KEY)).toBe('true')
  })

  it('restart() relance le tour depuis l\'étape 0', () => {
    const store = useOnboardingStore()
    // Simule un tour déjà complété
    store.complete()
    expect(store.isActive).toBe(false)

    store.restart()

    expect(store.isActive).toBe(true)
    expect(store.currentStep).toBe(0)
    // isDone reste true en localStorage (restart est explicite)
    expect(store.isDone).toBe(true)
  })

  it('isLastStep est vrai uniquement sur la dernière étape', () => {
    const store = useOnboardingStore()
    store.start()
    expect(store.isLastStep).toBe(false)

    store.currentStep = TOTAL_STEPS - 1
    expect(store.isLastStep).toBe(true)
  })

  it('STEP_SELECTORS contient le bon nombre de sélecteurs', () => {
    expect(STEP_SELECTORS.length).toBe(TOTAL_STEPS)
  })

  it('totalSteps correspond à TOTAL_STEPS', () => {
    const store = useOnboardingStore()
    expect(store.totalSteps).toBe(TOTAL_STEPS)
  })

  it('totalSteps est 5 (nombre d\'étapes défini)', () => {
    const store = useOnboardingStore()
    expect(store.totalSteps).toBe(5)
  })
})
