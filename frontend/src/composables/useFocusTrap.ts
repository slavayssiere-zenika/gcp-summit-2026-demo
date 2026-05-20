/**
 * useFocusTrap — Composable Vue 3 (WCAG 2.1 AA — critère 2.1.2)
 *
 * Confine la navigation clavier (Tab / Shift+Tab) à l'intérieur d'un élément
 * HTML cible quand le trap est actif. Restaure le focus sur l'élément déclencheur
 * (ou un fallback) à la désactivation.
 *
 * Usage :
 *   const { trapRef, activateTrap, deactivateTrap } = useFocusTrap()
 *   // Attacher trapRef à la ref de l'élément conteneur du modal
 *   // Appeler activateTrap() quand le modal s'ouvre, deactivateTrap() à la fermeture
 */
import { ref, onUnmounted } from 'vue'

const FOCUSABLE_SELECTORS = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(', ')


export function useFocusTrap() {
  const trapRef = ref<HTMLElement | null>(null)
  let previouslyFocused: HTMLElement | null = null

  const getFocusableElements = (): HTMLElement[] => {
    if (!trapRef.value) return []
    return Array.from(
      trapRef.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS)
    ).filter(el => !el.closest('[aria-hidden="true"]'))
  }

  const handleKeydown = (e: KeyboardEvent) => {
    if (e.key !== 'Tab') return

    const focusable = getFocusableElements()
    if (focusable.length === 0) {
      e.preventDefault()
      return
    }

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    const active = document.activeElement as HTMLElement

    if (e.shiftKey) {
      // Shift+Tab : si on est sur le premier élément, sauter au dernier
      if (active === first || !trapRef.value?.contains(active)) {
        e.preventDefault()
        last.focus()
      }
    } else {
      // Tab : si on est sur le dernier élément, revenir au premier
      if (active === last || !trapRef.value?.contains(active)) {
        e.preventDefault()
        first.focus()
      }
    }
  }

  const activateTrap = () => {
    // Mémoriser l'élément qui avait le focus avant l'ouverture du modal
    previouslyFocused = document.activeElement as HTMLElement

    document.addEventListener('keydown', handleKeydown)

    // Donner le focus au premier élément focusable du modal (nextTick-safe via setTimeout 0)
    setTimeout(() => {
      const focusable = getFocusableElements()
      if (focusable.length > 0) {
        focusable[0].focus()
      } else if (trapRef.value) {
        // Fallback : rendre le conteneur lui-même focusable si vide
        trapRef.value.setAttribute('tabindex', '-1')
        trapRef.value.focus()
      }
    }, 0)
  }

  const deactivateTrap = () => {
    document.removeEventListener('keydown', handleKeydown)

    // Restaurer le focus sur l'élément déclencheur
    if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
      previouslyFocused.focus()
    }
    previouslyFocused = null
  }

  // Nettoyage automatique si le composant parent est détruit sans appel explicite
  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeydown)
  })

  return { trapRef, activateTrap, deactivateTrap }
}
