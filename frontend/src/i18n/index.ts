import { createI18n } from 'vue-i18n'
import fr from './locales/fr'
import en from './locales/en'

export const LOCALE_KEY = 'zenika_locale'
export type SupportedLocale = 'fr' | 'en'
export const SUPPORTED_LOCALES: SupportedLocale[] = ['fr', 'en']

function detectLocale(): SupportedLocale {
  // 1. Préférence persistée par l'utilisateur
  const saved = localStorage.getItem(LOCALE_KEY) as SupportedLocale | null
  if (saved && SUPPORTED_LOCALES.includes(saved)) return saved

  // 2. Langue du navigateur (ex: "fr-FR" → "fr")
  const browserLang = navigator.language.split('-')[0] as SupportedLocale
  if (SUPPORTED_LOCALES.includes(browserLang)) return browserLang

  // 3. Fallback : français
  return 'fr'
}

export const i18n = createI18n({
  legacy: false,           // Composition API mode
  locale: detectLocale(),
  fallbackLocale: 'fr',
  messages: { fr, en },
})

export function setLocale(locale: SupportedLocale) {
  i18n.global.locale.value = locale
  localStorage.setItem(LOCALE_KEY, locale)
  document.documentElement.lang = locale
}

export function currentLocale(): SupportedLocale {
  return i18n.global.locale.value as SupportedLocale
}
