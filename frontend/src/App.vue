<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import {
  LogOut, User as UserIcon, Bot, Network, ServerCog, BookOpen,
  ChevronDown, Settings, BarChart3, Cpu, HardDriveUpload,
  Users, GitMerge, CalendarDays, BrainCircuit, RefreshCw,
  ShieldAlert, ShieldCheck, Briefcase, ExternalLink, Menu, X,
  AlertTriangle, HelpCircle
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { authService } from './services/auth'
import { useRouter } from 'vue-router'
import ToastNotification from '@/components/ui/ToastNotification.vue'
import LanguageSwitcher from '@/components/ui/LanguageSwitcher.vue'
import OnboardingTour from '@/components/onboarding/OnboardingTour.vue'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { useUxStore } from '@/stores/uxStore'
import axios from 'axios'

const { t } = useI18n()

const router = useRouter()
const searchQuery = ref('')
const searchSuggestions = ref<any[]>([])
const showSuggestions = ref(false)
const isSearching = ref(false)

const handleSearch = () => {
  if (searchQuery.value) {
    router.push({ path: '/', query: { q: searchQuery.value } })
    searchQuery.value = ''
    showSuggestions.value = false
  }
}

const fetchSuggestions = async () => {
  if (searchQuery.value.length < 3) {
    searchSuggestions.value = []
    return
  }
  isSearching.value = true
  try {
    const token = localStorage.getItem('token') || localStorage.getItem('access_token') || ''
    const res = await axios.get(`/api/users/search?query=${searchQuery.value}&limit=5`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    searchSuggestions.value = res.data.items || []
    showSuggestions.value = searchSuggestions.value.length > 0
  } catch (e) {
    console.error('Search failed', e)
  } finally {
    isSearching.value = false
  }
}

const selectSuggestion = (user: any) => {
  router.push(`/user/${user.id}`)
  searchQuery.value = ''
  showSuggestions.value = false
}

watch(searchQuery, () => {
  fetchSuggestions()
})

const handleLogout = async () => {
  await authService.logout()
}

const isAdmin = () => authService.state.user?.role === 'admin'
const isRh = () => authService.state.user?.role === 'rh' || isAdmin()

const onboardingStore = useOnboardingStore()
const uxStore = useUxStore()

const isMobileMenuOpen = ref(false)
const toggleMobileMenu = () => {
  isMobileMenuOpen.value = !isMobileMenuOpen.value
}

// Déclenche le tour automatiquement à la première connexion
watch(
  () => authService.state.isAuthenticated,
  (authenticated) => {
    if (authenticated && !onboardingStore.isDone) {
      setTimeout(() => onboardingStore.start(), 900)
    }
  },
  { immediate: true }
)

watch(() => router.currentRoute.value.path, () => {
  isMobileMenuOpen.value = false
})

// ── Data Quality Banner ───────────────────────────────────────────────────────
const isDataQualityBad = ref(false)
let _dqPollingTimer: ReturnType<typeof setInterval> | null = null

const checkDataQuality = async () => {
  if (!authService.state.isAuthenticated) return
  try {
    const token = localStorage.getItem('token') || localStorage.getItem('access_token') || ''
    const res = await axios.get('/api/cv/bulk-reanalyse/data-quality', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    const data = res.data
    // Afficher le bandeau uniquement si le score global est dégradé (grade < A, soit score < 85).
    // Les anomalies mineures ont leur propre section dans le dashboard — elles ne dégradent
    // pas le score global et ne doivent pas déclencher le bandeau d'alerte.
    isDataQualityBad.value = !!(data && data.score < 85)
  } catch (e) {
    console.error('Data quality check failed', e)
    // En cas d'erreur réseau : ne pas modifier l'état courant
  }
}

// Démarre le polling dès que l'utilisateur est authentifié
watch(
  () => authService.state.isAuthenticated,
  (authenticated) => {
    if (authenticated) {
      checkDataQuality()
      if (!_dqPollingTimer) {
        _dqPollingTimer = setInterval(checkDataQuality, 60_000)
      }
    } else {
      isDataQualityBad.value = false
      if (_dqPollingTimer) {
        clearInterval(_dqPollingTimer)
        _dqPollingTimer = null
      }
    }
  },
  { immediate: true }
)

const showLoading = ref(false)
const isColdStart = ref(false)
const isInitialLoad = ref(true)
let loadingTimer: ReturnType<typeof setTimeout> | null = null
let coldStartTimer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  if (authService.state.isLoading) {
    loadingTimer = setTimeout(() => {
      showLoading.value = true
    }, 800)
    
    coldStartTimer = setTimeout(() => {
      isColdStart.value = true
    }, 3000)
  }
})

watch(
  () => authService.state.isLoading,
  (loading) => {
    if (!loading) {
      if (loadingTimer) clearTimeout(loadingTimer)
      if (coldStartTimer) clearTimeout(coldStartTimer)
      showLoading.value = false
      isColdStart.value = false
      isInitialLoad.value = false
    }
  }
)

onUnmounted(() => {
  if (loadingTimer) clearTimeout(loadingTimer)
  if (coldStartTimer) clearTimeout(coldStartTimer)
  if (_dqPollingTimer) {
    clearInterval(_dqPollingTimer)
    _dqPollingTimer = null
  }
})
</script>

<template>
  <div id="main-app">
    <a href="#main-content" class="skip-link">{{ t('nav.skip_to_content') || 'Aller au contenu principal' }}</a>
    <ToastNotification />
    <!-- Tour guidé onboarding — Teleport vers body -->
    <OnboardingTour />
    <div class="header">
      <div class="header-left">
        <div class="logo">ZENIKA</div>
        <div class="subtitle hide-on-mobile">Console Intelligent Agent</div>
      </div>
      
      <button class="mobile-menu-btn" @click="toggleMobileMenu" v-if="authService.state.isAuthenticated && router.currentRoute.value.path !== '/warming'" aria-label="Menu">
        <X v-if="isMobileMenuOpen" size="24" />
        <Menu v-else size="24" />
      </button>

      <div class="nav-links" :class="{ 'is-open': isMobileMenuOpen }" v-if="router.currentRoute.value.path !== '/warming'">
        <!-- Quick Search -->
        <div v-if="authService.state.isAuthenticated" class="header-search">
          <div class="search-input-wrapper">
            <input
              type="text"
              v-model="searchQuery"
              @keyup.enter="handleSearch"
              @focus="showSuggestions = searchQuery.length >= 3"
              @blur="setTimeout(() => showSuggestions = false, 200)"
              :placeholder="t('nav.search_placeholder')"
              :aria-label="t('nav.search_aria')"
            />
            <div v-if="isSearching" class="search-spinner"></div>
          </div>
          <Transition name="slide-fade">
            <div v-if="showSuggestions" class="search-results-dropdown glass-card">
              <div
                v-for="user in searchSuggestions"
                :key="user.id"
                class="search-result-item"
                @click="selectSuggestion(user)"
              >
                <div class="result-avatar">
                  <UserIcon size="14" />
                </div>
                <div class="result-info">
                  <div class="result-name">{{ user.full_name || user.username }}</div>
                  <div class="result-role">{{ user.role }}</div>
                </div>
              </div>
            </div>
          </Transition>
        </div>

        <div class="nav-pills" v-if="authService.state.isAuthenticated">

          <!-- Agent IA -->
          <RouterLink to="/" class="nav-pill" active-class="active" :aria-label="t('nav.agent')">
            <Bot size="15" /> {{ t('nav.agent') }}
          </RouterLink>

          <!-- Arbre des compétences -->
          <RouterLink to="/competencies" class="nav-pill" active-class="active" :aria-label="t('nav.competencies')">
            <Network size="15" /> {{ t('nav.competencies') }}
          </RouterLink>

          <!-- Hub RH (consultants, compétences) -->
          <div class="dropdown" v-if="isRh()">
            <button class="nav-pill dropdown-btn" :class="{ active: ['/user', '/admin/deduplication', '/admin/availability', '/admin/skills-to-acquire'].some(p => router.currentRoute.value.path.startsWith(p)) }" aria-label="Hub RH">
              <Users size="15" /> {{ t('nav.hub_rh') }} <ChevronDown size="13" />
            </button>
            <div class="dropdown-content">
              <div class="dropdown-section-label">{{ t('nav.section_consultants') }}</div>
              <RouterLink to="/" class="nav-pill" :aria-label="t('nav.hr_search_agent')">
                <Bot size="13" /> {{ t('nav.hr_search_agent') }}
              </RouterLink>
              <div class="dropdown-section-label">{{ t('nav.section_hr') }}</div>
              <RouterLink to="/admin/availability" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.hr_planning')">
                <CalendarDays size="13" /> {{ t('nav.hr_planning') }}
              </RouterLink>
              <RouterLink to="/admin/deduplication" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.hr_dedup')">
                <GitMerge size="13" /> {{ t('nav.hr_dedup') }}
              </RouterLink>
              <RouterLink to="/admin/skills-to-acquire" class="nav-pill" active-class="dropdown-active" aria-label="Compétences clés à acquérir">
                <BrainCircuit size="13" /> Compétences clés à acquérir
              </RouterLink>
            </div>
          </div>

          <!-- Missions -->
          <RouterLink to="/missions" class="nav-pill" active-class="active" :aria-label="t('nav.missions')">
            <Briefcase size="15" /> {{ t('nav.missions') }}
          </RouterLink>

          <!-- Administration (admin only) -->
          <div class="dropdown" v-if="isAdmin()">
            <button
              class="nav-pill admin-pill dropdown-btn"
              :class="{ active: router.currentRoute.value.path.startsWith('/admin') }"
              :aria-label="t('nav.admin')"
            >
              <Settings size="15" /> {{ t('nav.admin') }} <ChevronDown size="13" />
            </button>
            <div class="dropdown-content dropdown-wide">
              <div class="dropdown-section-label">{{ t('nav.section_pipeline') }}</div>
              <RouterLink to="/admin" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.admin_import_drive')">
                <HardDriveUpload size="13" /> {{ t('nav.admin_import_drive') }}
              </RouterLink>
              <RouterLink to="/import-cv" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.admin_import_manual')">
                <BookOpen size="13" /> {{ t('nav.admin_import_manual') }}
              </RouterLink>
              <RouterLink to="/admin/extraction-quality" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.admin_extraction_quality')">
                <ShieldCheck size="13" /> {{ t('nav.admin_extraction_quality') }}
              </RouterLink>
              <RouterLink to="/admin/reanalysis" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.admin_taxonomy')">
                <Network size="13" /> {{ t('nav.admin_taxonomy') }}
              </RouterLink>
              <RouterLink to="/admin/bulk-import" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.admin_bulk')">
                <RefreshCw size="13" /> {{ t('nav.admin_bulk') }}
              </RouterLink>

              <div class="dropdown-section-label">{{ t('nav.section_agents_config') }}</div>
              <RouterLink to="/admin/prompts" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.admin_prompts')">
                <BrainCircuit size="13" /> {{ t('nav.admin_prompts') }}
              </RouterLink>

              <div class="dropdown-section-label">{{ t('nav.section_users_security') }}</div>
              <RouterLink to="/admin/users" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.admin_users')">
                <Users size="13" /> {{ t('nav.admin_users') }}
              </RouterLink>
              <RouterLink to="/admin/finops" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.admin_finops')">
                <ShieldAlert size="13" /> {{ t('nav.admin_finops') }}
              </RouterLink>
            </div>
          </div>

          <!-- Outils Techniques / Documentation -->
          <div class="dropdown">
            <button class="nav-pill dropdown-btn" :aria-label="t('nav.docs')">
              <BookOpen size="15" /> {{ t('nav.docs') }} <ChevronDown size="13" />
            </button>
            <div class="dropdown-content dropdown-wide">
              <div class="dropdown-section-label">{{ t('nav.section_doc') }}</div>
              <RouterLink to="/help" class="nav-pill" active-class="dropdown-active">
                <BookOpen size="13" /> {{ t('nav.docs_help') }}
              </RouterLink>
              <RouterLink to="/docs/agents" class="nav-pill" active-class="dropdown-active">
                <Cpu size="13" /> {{ t('nav.docs_agents') }}
              </RouterLink>
              <RouterLink to="/specs" class="nav-pill" active-class="dropdown-active">
                <BookOpen size="13" /> {{ t('nav.docs_specs') }}
              </RouterLink>

              <div class="dropdown-section-label">{{ t('nav.section_observability') }}</div>
              <RouterLink to="/infrastructure" class="nav-pill" active-class="dropdown-active">
                <Network size="13" /> {{ t('nav.docs_infra') }}
              </RouterLink>
              <RouterLink to="/aiops" class="nav-pill" active-class="dropdown-active">
                <BarChart3 size="13" /> {{ t('nav.docs_aiops') }}
              </RouterLink>
              <RouterLink to="/registry" class="nav-pill" active-class="dropdown-active">
                <ServerCog size="13" /> {{ t('nav.docs_mcp') }}
              </RouterLink>
              <RouterLink to="/data-quality" class="nav-pill" active-class="dropdown-active" :aria-label="t('nav.docs_data_quality')">
                <ShieldCheck size="13" /> {{ t('nav.docs_data_quality') }}
              </RouterLink>

              <div class="dropdown-section-label" v-if="isAdmin()">{{ t('nav.section_swagger') }}</div>
              <template v-if="isAdmin()">
                <a href="/api/users/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Users API">
                  <ExternalLink size="12" /> Users API
                </a>
                <a href="/api/cv/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger CV API">
                  <ExternalLink size="12" /> CV API
                </a>
                <a href="/api/competencies/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Competencies API">
                  <ExternalLink size="12" /> Competencies API
                </a>
                <a href="/api/drive/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Drive API">
                  <ExternalLink size="12" /> Drive API
                </a>
                <a href="/api/prompts/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Prompts API">
                  <ExternalLink size="12" /> Prompts API
                </a>
                <a href="/api/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Agent Router API">
                  <ExternalLink size="12" /> Agent Router API
                </a>
                <a href="/api/missions/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Missions API">
                  <ExternalLink size="12" /> Missions API
                </a>
                <a href="/api/items/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Items API">
                  <ExternalLink size="12" /> Items API
                </a>
              </template>
            </div>
          </div>

        </div>

        <div v-if="authService.state.isAuthenticated" class="separator"></div>

        <!-- Sélecteur de langue -->
        <LanguageSwitcher v-if="authService.state.isAuthenticated" />

        <!-- SRE Admin-only degraded services warning pill -->
        <button
          v-if="authService.state.user?.role === 'admin' && uxStore.degradedServices.length > 0"
          class="sre-degraded-badge"
          @click="router.push('/data-quality')"
          :title="t('nav.degraded_services_tip', { count: uxStore.degradedServices.length, list: uxStore.degradedServices.join(', ') }) || `Avertissement SRE : ${uxStore.degradedServices.length} service(s) froid(s) ou dégradé(s) (${uxStore.degradedServices.join(', ')}). Cliquez pour analyser.`"
        >
          <AlertTriangle size="16" class="sre-warning-icon" />
          <span class="sre-badge-count">{{ uxStore.degradedServices.length }}</span>
        </button>

        <!-- Bouton "?" — relance le tour guidé à tout moment -->
        <button
          v-if="authService.state.isAuthenticated"
          class="help-tour-btn"
          @click="onboardingStore.restart()"
          :title="t('nav.help_tour')"
          :aria-label="t('nav.help_tour')"
        >
          <HelpCircle size="17" />
        </button>

        <div v-if="authService.state.isAuthenticated" class="user-profile">
          <RouterLink to="/profile" class="user-info-link nav-pill user-pill">
            <UserIcon size="15" />
            <span>{{ authService.state.user?.full_name }}</span>
          </RouterLink>
          <button @click="handleLogout" class="logout-pill" :title="t('nav.logout')" :aria-label="t('nav.logout')">
            <LogOut size="15" />
          </button>
        </div>
      </div>
    </div>

    <div v-if="isDataQualityBad" class="data-quality-banner">
      <AlertTriangle size="18" />
      <span><strong>{{ t('nav.dq_warning') }}</strong> {{ t('nav.dq_message') }}</span>
      <RouterLink to="/data-quality" class="data-quality-link">{{ t('nav.dq_detail') }}</RouterLink>
    </div>

    <main id="main-content" class="content">
      <div v-if="authService.state.isLoading && showLoading && isInitialLoad" class="init-loading-container glass" role="status" :aria-label="t('init.title')">
        <div class="init-loading-card">
          <div class="init-spinner-wrapper">
            <div class="init-spinner"></div>
            <Bot size="32" class="init-bot-icon" aria-hidden="true" />
          </div>
          <h2>{{ t('init.title') }}</h2>
          <p class="init-status">{{ t('init.checking') }}</p>
          
          <transition name="fade">
            <div v-if="isColdStart" class="cold-start-warning">
              <AlertTriangle size="20" class="warning-icon" aria-hidden="true" />
              <div>
                <strong>{{ t('init.cold_start_title') }}</strong>
                <p>{{ t('init.cold_start_desc') }}</p>
              </div>
            </div>
          </transition>
        </div>
      </div>
      <RouterView v-else />
    </main>
  </div>
</template>

<style>
/* Variables moved to style.css */

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  background: var(--bg-gradient);
  color: var(--text-primary);
  min-height: 100vh;
}

#main-app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.header {
  background: var(--header-bg);
  backdrop-filter: blur(12px);
  padding: 1rem 1.5rem;
  display: flex;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 100;
  border-bottom: 2px solid var(--zenika-red);
  box-shadow: var(--shadow-sm-app);
}

.logo {
  font-weight: 800;
  font-size: 1.5rem;
  letter-spacing: -0.5px;
  color: var(--zenika-red);
  margin-right: 1rem;
}

.subtitle {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary);
  opacity: 0.8;
  padding-left: 1rem;
  border-left: 1px solid #e0e0e0;
}

/* Caché en dessous de 1600px pour gagner de la place */
@media (max-width: 1600px) {
  .subtitle { display: none; }
}

.nav-links {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex-shrink: 1;
}

.nav-pills {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(0, 0, 0, 0.03);
  padding: 4px;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.nav-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 8px;
  color: var(--text-secondary);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.82rem;
  transition: all 0.25s ease;
  white-space: nowrap;
}

.nav-pill:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--zenika-red);
  transform: translateY(-2px);
}

.nav-pill.active {
  background: #fff;
  color: var(--zenika-red);
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.1);
  font-weight: 600;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 6px;
}

.user-pill {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
}

.user-pill:hover {
  border-color: rgba(227, 25, 55, 0.3);
}

.logout-pill {
  background: rgba(227, 25, 55, 0.05);
  border: 1px solid rgba(227, 25, 55, 0.1);
  color: var(--zenika-red);
  width: 44px;
  height: 44px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.logout-pill:hover {
  background: var(--zenika-red);
  color: #fff;
}
.nav-links a {
  text-decoration: none;
  color: var(--text-secondary);
  font-weight: 500;
  font-size: 0.9rem;
  padding: 0.5rem 0.9rem;
  border-radius: 12px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.nav-links a:hover {
  background: rgba(227, 25, 55, 0.05);
  color: var(--zenika-red);
}

.nav-links a.active {
  background: var(--zenika-red);
  color: white;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.2);
}

/* Dropdown Menu CSS */
.dropdown {
  position: relative;
  display: inline-block;
}

.dropdown-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
}

.dropdown-content {
  display: none;
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  background-color: var(--header-bg);
  min-width: 240px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.13);
  border-radius: 14px;
  z-index: 1000;
  border: 1px solid rgba(0, 0, 0, 0.07);
  padding: 8px;
  flex-direction: column;
  gap: 2px;
  backdrop-filter: blur(12px);
}

.dropdown-content::before {
  content: '';
  position: absolute;
  top: -15px; /* Bridge the gap */
  left: 0;
  right: 0;
  height: 15px;
}

.dropdown-wide {
  min-width: 280px;
}

/* Align right-side dropdowns to prevent overflow */
.dropdown:last-of-type .dropdown-content,
.dropdown:nth-last-of-type(2) .dropdown-content {
  left: auto;
  right: 0;
}

.dropdown:hover .dropdown-content {
  display: flex;
}

.dropdown-content .nav-pill {
  width: 100%;
  justify-content: flex-start;
  white-space: nowrap;
  font-size: 0.85rem;
  padding: 7px 12px;
  border-radius: 8px;
  gap: 9px;
}

.dropdown-section-label {
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #94a3b8;
  padding: 8px 12px 4px;
  margin-top: 2px;
}

.dropdown-section-label:first-child {
  margin-top: 0;
  padding-top: 4px;
}

.dropdown-divider {
  height: 1px;
  background: rgba(0,0,0,0.06);
  margin: 4px 0;
}

.dropdown-active {
  background: rgba(227, 25, 55, 0.07);
  color: var(--zenika-red);
  font-weight: 600;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 1rem;
  background: white;
  padding: 0.4rem 0.5rem 0.4rem 1rem;
  border-radius: 16px;
  border: 1.5px solid #eee;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
}

.logout-btn {
  background: #f5f5f5;
  border: none;
  color: #666;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.logout-btn:hover {
  background: #fff5f5;
  color: var(--zenika-red);
  transform: scale(1.05);
}

/* ── F7 — Bouton tour guidé "?" ─────────────────────────────── */
.help-tour-btn {
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.07);
  color: #94a3b8;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.help-tour-btn:hover {
  background: rgba(227, 25, 55, 0.07);
  border-color: rgba(227, 25, 55, 0.25);
  color: var(--zenika-red);
  transform: rotate(15deg);
}

/* SRE Degraded Badge for Admin */
.sre-degraded-badge {
  background: rgba(245, 158, 11, 0.08);
  border: 1.5px solid rgba(245, 158, 11, 0.25);
  color: #f59e0b;
  height: 38px;
  padding: 0 0.75rem;
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
  animation: srePulse 2s infinite;
}

.sre-degraded-badge:hover {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.5);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.15);
}

.sre-warning-icon {
  animation: sreShake 4s infinite;
}

.sre-badge-count {
  font-size: 0.8rem;
  font-weight: 700;
}

@keyframes srePulse {
  0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.2); }
  70% { box-shadow: 0 0 0 6px rgba(245, 158, 11, 0); }
  100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
}

@keyframes sreShake {
  0%, 90%, 100% { transform: rotate(0deg); }
  92% { transform: rotate(-8deg); }
  94% { transform: rotate(8deg); }
  96% { transform: rotate(-8deg); }
  98% { transform: rotate(8deg); }
}

.separator {
  width: 1px;
  height: 24px;
  background: #e0e0e0;
  margin: 0 0.75rem;
}

.swagger-links {
  display: flex;
  gap: 0.4rem;
  background: rgba(0, 0, 0, 0.03);
  padding: 0.3rem;
  border-radius: 14px;
}

.swagger-link {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  border: 1px solid transparent;
}

.swagger-link:hover {
  background: white;
  border-color: #ddd;
  box-shadow: var(--shadow-sm-app);
  color: var(--zenika-red);
}

.header-search {
  position: relative;
  margin-right: 1.5rem;
  z-index: 1001;
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.header-search input {
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.08);
  padding: 0.6rem 1.2rem;
  padding-right: 2.5rem;
  border-radius: 24px;
  font-size: 0.85rem;
  width: 220px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  color: var(--text-primary);
}

.header-search input:focus {
  background: #fff;
  width: 320px;
  outline: none;
  border-color: var(--gemini-purple);
  box-shadow: 0 0 0 4px rgba(142, 117, 255, 0.1), var(--shadow-md);
  transform: translateY(-1px);
}

.search-spinner {
  position: absolute;
  right: 12px;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(0,0,0,0.1);
  border-top-color: var(--gemini-purple);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.search-results-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  max-height: 400px;
  overflow-y: auto;
  z-index: 1002;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.search-result-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.search-result-item:hover {
  background: rgba(142, 117, 255, 0.08);
  transform: translateX(4px);
}

.result-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--gemini-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.result-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.result-name {
  font-weight: 700;
  font-size: 0.9rem;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-role {
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: capitalize;
}

/* Transitions */
.slide-fade-enter-active {
  transition: all 0.3s ease-out;
}
.slide-fade-leave-active {
  transition: all 0.2s cubic-bezier(1, 0.5, 0.8, 1);
}
.slide-fade-enter-from,
.slide-fade-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.content {
  flex: 1;
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}
.admin-pill {
  border: 1px solid rgba(227, 25, 55, 0.2);
  background: rgba(227, 25, 55, 0.05);
}
.admin-pill:hover {
  background: rgba(227, 25, 55, 0.1);
  border-color: rgba(227, 25, 55, 0.4);
}
.admin-pill.active {
  background: var(--zenika-red);
  color: white;
  border-color: var(--zenika-red);
}

/* Responsive Styles */
/* Responsive — hamburger à ≤ 1280px */
@media (max-width: 1280px) {
  .header {
    padding: 1rem 1.5rem;
  }
  .mobile-menu-btn {
    display: flex;
    background: transparent;
    border: none;
    color: var(--zenika-red);
    cursor: pointer;
    padding: 0.5rem;
    margin-left: auto;
  }
  .nav-links {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    flex-direction: column;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(12px);
    padding: 1.5rem;
    box-shadow: 0 10px 20px rgba(0,0,0,0.1);
    align-items: stretch;
    max-height: calc(100vh - 70px);
    overflow-y: auto;
  }
  .nav-links.is-open {
    display: flex;
  }
  .nav-pills {
    flex-direction: column;
    width: 100%;
  }
  .nav-pill {
    width: 100%;
    justify-content: flex-start;
    padding: 1rem;
  }
  .header-search {
    margin-right: 0;
    margin-bottom: 1rem;
    width: 100%;
  }
  .header-search input {
    width: 100%;
  }
  .header-search input:focus {
    width: 100%;
    transform: none;
  }
  .dropdown {
    width: 100%;
  }
  .dropdown-btn {
    width: 100%;
  }
  .dropdown:hover .dropdown-content, .dropdown:focus-within .dropdown-content {
    position: static;
    box-shadow: none;
    border: none;
    margin-top: 0.5rem;
    background: rgba(0,0,0,0.02);
    display: flex;
  }
  .dropdown-content::before {
    display: none;
  }
  .user-profile {
    width: 100%;
    justify-content: space-between;
    margin-top: 1rem;
  }
  .separator {
    display: none;
  }
  .content {
    padding: 1rem;
  }
}

@media (min-width: 1025px) {
  .mobile-menu-btn {
    display: none;
  }
  .header-left {
    display: flex;
    align-items: center;
  }
}

.data-quality-banner {
  background: #fffbeb;
  color: #b45309;
  padding: 0.75rem 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  font-size: 0.9rem;
  border-bottom: 1px solid #fef3c7;
  box-shadow: inset 0 -1px 0 rgba(217, 119, 6, 0.1);
  animation: slideDown 0.3s ease-out;
}

.data-quality-banner strong {
  font-weight: 700;
}

.data-quality-link {
  color: #b45309;
  font-weight: 600;
  text-decoration: underline;
  margin-left: 0.5rem;
  transition: color 0.2s;
}

.data-quality-link:hover {
  color: #92400e;
}

@keyframes slideDown {
  from { transform: translateY(-10px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

/* Initial loading and cold start styles */
.init-loading-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 200px);
  padding: 2.5rem;
  border-radius: 24px;
  animation: fadeIn 0.4s ease-out;
  margin: 2rem auto;
  max-width: 600px;
}

.init-loading-card {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
  width: 100%;
}

.init-spinner-wrapper {
  position: relative;
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.init-spinner {
  position: absolute;
  width: 100%;
  height: 100%;
  border: 4px solid rgba(227, 25, 55, 0.1);
  border-radius: 50%;
  border-top-color: var(--zenika-red);
  animation: spin 1s cubic-bezier(0.5, 0.1, 0.4, 0.9) infinite;
}

.init-bot-icon {
  color: var(--zenika-red);
  animation: pulseIcon 2s ease-in-out infinite;
}

.init-loading-card h2 {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

.init-status {
  font-size: 0.95rem;
  color: var(--color-text-secondary);
  margin: 0;
}

.cold-start-warning {
  margin-top: 1rem;
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  background: #fffbeb;
  border: 1px solid #fef3c7;
  padding: 1.25rem;
  border-radius: 16px;
  color: #b45309;
  text-align: left;
  animation: slideUp 0.3s ease-out;
  box-shadow: 0 4px 12px rgba(217, 119, 6, 0.05);
}

.cold-start-warning .warning-icon {
  color: #d97706;
  flex-shrink: 0;
  margin-top: 2px;
  animation: sreShake 4s infinite;
}

.cold-start-warning strong {
  font-size: 0.9rem;
  font-weight: 700;
  display: block;
  margin-bottom: 0.25rem;
}

.cold-start-warning p {
  font-size: 0.85rem;
  color: #b45309;
  margin: 0;
  line-height: 1.4;
}

@keyframes pulseIcon {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.1); opacity: 0.8; }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
