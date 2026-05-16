/**
 * Test utilities — Setup global plugins for vue-i18n v11+
 *
 * vue-i18n v11 requiert que le plugin soit installé via app.use()
 * avant tout appel à useI18n(). Ce setup configure @vue/test-utils
 * pour injecter automatiquement i18n dans chaque test.
 *
 * On crée une instance dédiée aux tests (sans accès à localStorage)
 * avec le même helper escapeAtSign() que l'application.
 */
import { config } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import fr from '../i18n/locales/fr'
import en from '../i18n/locales/en'

// Même helper que src/i18n/index.ts — escape les @ littéraux pour vue-i18n v11
function escapeAtSign(messages: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(messages)) {
    if (typeof value === 'string') {
      result[key] = value.replace(/@(?!:)/g, "{'@'}")
    } else if (typeof value === 'object' && value !== null) {
      result[key] = escapeAtSign(value as Record<string, unknown>)
    } else {
      result[key] = value
    }
  }
  return result
}

// Instance i18n dédiée aux tests (pas d'accès localStorage, locale fixe fr)
const testI18n = createI18n({
  legacy: false,
  locale: 'fr',
  fallbackLocale: 'fr',
  messages: {
    fr: escapeAtSign(fr) as typeof fr,
    en: escapeAtSign(en) as typeof en,
  },
  warnHtmlMessage: false,
})

// Injection automatique dans tous les mount() de @vue/test-utils
config.global.plugins = [testI18n]
