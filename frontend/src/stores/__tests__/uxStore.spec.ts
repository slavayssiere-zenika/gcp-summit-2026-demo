import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useUxStore } from '../uxStore'

describe('useUxStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('doit démarrer avec un tableau de toasts vide', () => {
    const store = useUxStore()
    expect(store.toasts).toEqual([])
    expect(store.toastIdCounter).toBe(0)
  })

  it('doit ajouter un toast via showToast', () => {
    const store = useUxStore()
    store.showToast('Opération réussie', 'success')

    expect(store.toasts).toHaveLength(1)
    expect(store.toasts[0].message).toBe('Opération réussie')
    expect(store.toasts[0].type).toBe('success')
    expect(store.toasts[0].id).toBe(0)
  })

  it('doit incrémenter l\'id à chaque nouveau toast', () => {
    const store = useUxStore()
    store.showToast('Toast 1', 'info')
    store.showToast('Toast 2', 'error')

    expect(store.toasts[0].id).toBe(0)
    expect(store.toasts[1].id).toBe(1)
  })

  it('doit utiliser le type "info" par défaut', () => {
    const store = useUxStore()
    store.showToast('Message sans type')

    expect(store.toasts[0].type).toBe('info')
  })

  it('doit supprimer automatiquement un toast après 5 secondes', () => {
    const store = useUxStore()
    store.showToast('Toast temporaire', 'warning')
    expect(store.toasts).toHaveLength(1)

    vi.advanceTimersByTime(5000)
    expect(store.toasts).toHaveLength(0)
  })

  it('doit supprimer un toast manuellement via removeToast', () => {
    const store = useUxStore()
    store.showToast('Toast A', 'info')
    store.showToast('Toast B', 'info')
    expect(store.toasts).toHaveLength(2)

    store.removeToast(0)
    expect(store.toasts).toHaveLength(1)
    expect(store.toasts[0].message).toBe('Toast B')
  })

  it('doit ne rien faire si removeToast cible un id inexistant', () => {
    const store = useUxStore()
    store.showToast('Toast unique', 'success')
    store.removeToast(999)
    expect(store.toasts).toHaveLength(1)
  })
})
