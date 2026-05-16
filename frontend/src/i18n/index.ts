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

// Pre-process messages to escape @ characters that are not followed
// by a vue-i18n linked message syntax (@:key). This ensures compatibility
// with vue-i18n v11's stricter message compiler without requiring
// changes to all translation strings.
function escapeAtSign(messages: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(messages)) {
    if (typeof value === 'string') {
      // Replace @ not followed by : (linked message syntax) with literal @
      // We use a regex that identifies "@" not part of "@:key" patterns
      result[key] = value.replace(/@(?!:)/g, "{'@'}")
    } else if (typeof value === 'object' && value !== null) {
      result[key] = escapeAtSign(value as Record<string, unknown>)
    } else {
      result[key] = value
    }
  }
  return result
}

export const i18n = createI18n({
  legacy: false,           // Composition API mode (requis pour useI18n())
  locale: detectLocale(),
  fallbackLocale: 'fr',
  messages: {
    fr: escapeAtSign(fr) as typeof fr,
    en: escapeAtSign(en) as typeof en,
  },
  warnHtmlMessage: false,
})

export function setLocale(locale: SupportedLocale) {
  i18n.global.locale.value = locale
  localStorage.setItem(LOCALE_KEY, locale)
  document.documentElement.lang = locale
}

export function currentLocale(): SupportedLocale {
  return i18n.global.locale.value as SupportedLocale
}
