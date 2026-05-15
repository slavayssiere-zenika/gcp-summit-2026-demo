<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { setLocale, currentLocale, SUPPORTED_LOCALES, type SupportedLocale } from '@/i18n'

const { locale } = useI18n()

function switchTo(lang: SupportedLocale) {
  setLocale(lang)
}
</script>

<template>
  <div class="lang-switcher" role="group" aria-label="Sélecteur de langue">
    <button
      v-for="lang in SUPPORTED_LOCALES"
      :key="lang"
      class="lang-btn"
      :class="{ active: locale === lang }"
      @click="switchTo(lang)"
      :aria-pressed="locale === lang"
      :aria-label="lang === 'fr' ? 'Langue française' : 'English language'"
    >
      {{ lang.toUpperCase() }}
    </button>
  </div>
</template>

<style scoped>
.lang-switcher {
  display: flex;
  align-items: center;
  gap: 2px;
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.07);
  border-radius: 8px;
  padding: 3px;
  flex-shrink: 0;
}

.lang-btn {
  background: none;
  border: none;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: #94a3b8;
  padding: 0.25rem 0.45rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  line-height: 1;
}

.lang-btn:hover {
  color: #475569;
  background: rgba(0, 0, 0, 0.04);
}

.lang-btn.active {
  background: white;
  color: var(--zenika-red, #e31937);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
</style>
