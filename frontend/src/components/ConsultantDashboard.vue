<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import axios from 'axios'
import { useI18n } from 'vue-i18n'
import { 
  User as UserIcon, 
  Mail, 
  Briefcase, 
  Award, 
  History, 
  GraduationCap, 
  FileText,
  ShieldCheck,
  Calendar,
  ChevronRight,
  TrendingUp,
  Cpu,
  Clock,
  ExternalLink,
  BrainCircuit,
  Star,
  Sparkles,
  Info,
  Settings,
  MessageSquare,
  XCircle,
  Plus,
  Check,
  Eye,
  EyeOff,
  Copy
} from 'lucide-vue-next'
import { authService } from '../services/auth'
import CompetencyEvaluationPanel from './CompetencyEvaluationPanel.vue'

const props = defineProps<{
  userId: number | string
  readonly?: boolean
}>()

const { t } = useI18n()
const activeTab = ref<'overview' | 'experience' | 'skills' | 'docs' | 'settings'>('overview')

// State
const user = ref<any>(null)
const cvProfile = ref<any>(null)
const missions = ref<any[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const userTagsMap = ref<Record<string, string>>({})

// Settings state (moved from Profile.vue)
const personalPrompt = ref('')
const isSavingPrompt = ref(false)
const promptSaveSuccess = ref(false)
const promptSaveError = ref(false)

const unavailabilityPeriods = ref<any[]>([])
const newPeriod = ref({ start_date: '', end_date: '', type: 'full', reason: 'client' })
const isSavingAvailability = ref(false)

const jwtVisible = ref(false)
const jwtCopied = ref(false)
const jwtToken = ref(localStorage.getItem('access_token') || '')

// Computed
const userInitials = computed(() => {
  if (!user.value) return '??'
  const name = user.value.full_name || user.value.username || ''
  return name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
})

const seniorityLevel = computed(() => {
  const level = cvProfile.value?.seniority?.toLowerCase()
  if (level?.includes('senior')) return 'Senior'
  if (level?.includes('lead')) return 'Lead'
  if (level?.includes('expert')) return 'Expert'
  if (level?.includes('junior')) return 'Junior'
  return level || 'Confirmé'
})

const isOwner = computed(() => {
  return authService.state.user?.id?.toString() === props.userId?.toString()
})

const userAgency = computed(() => {
  if (!user.value || !user.value.id) return null
  return userTagsMap.value[user.value.id.toString()] || null
})

const maskedToken = computed(() => {
  if (!jwtToken.value) return 'Token introuvable'
  if (jwtVisible.value) return jwtToken.value
  return jwtToken.value.slice(0, 20) + '••••••••••••••••••••' + jwtToken.value.slice(-10)
})

const reasonLabel: Record<string, string> = {
  client: '💼 Client', vacances: '🏖️ Vacances', formation: '📚 Formation'
}
const typeLabel: Record<string, string> = {
  full: 'Journée', am: 'Matin', pm: 'Après-midi'
}

// Actions
const fetchUserTags = async () => {
  try {
    const response = await axios.get('/api/cv/users/tags/map')
    userTagsMap.value = response.data || {}
  } catch (err) {
    console.error('Failed to fetch user tags mapping:', err)
  }
}

const fetchPersonalPrompt = async () => {
  if (!isOwner.value) return
  try {
    const response = await axios.get('/api/prompts/user/me')
    personalPrompt.value = response.data.value || ''
  } catch {}
}

const savePersonalPrompt = async () => {
  isSavingPrompt.value = true
  promptSaveSuccess.value = false
  promptSaveError.value = false
  try {
    await axios.put('/api/prompts/user/me', { value: personalPrompt.value })
    promptSaveSuccess.value = true
    setTimeout(() => { promptSaveSuccess.value = false }, 3000)
  } catch {
    promptSaveError.value = true
    setTimeout(() => { promptSaveError.value = false }, 3000)
  } finally {
    isSavingPrompt.value = false
  }
}

const addAvailability = async () => {
  if (!newPeriod.value.start_date || !newPeriod.value.end_date) return
  const updatedPeriods = [...unavailabilityPeriods.value, { ...newPeriod.value }]
  isSavingAvailability.value = true
  try {
    await axios.put(`/api/users/${user.value.id}`, { unavailability_periods: updatedPeriods })
    unavailabilityPeriods.value = updatedPeriods
    newPeriod.value = { start_date: '', end_date: '', type: 'full', reason: 'client' }
  } catch (e) { console.error(e) } finally {
    isSavingAvailability.value = false
  }
}

const removeAvailability = async (index: number) => {
  const updatedPeriods = [...unavailabilityPeriods.value]
  updatedPeriods.splice(index, 1)
  try {
    await axios.put(`/api/users/${user.value.id}`, { unavailability_periods: updatedPeriods })
    unavailabilityPeriods.value = updatedPeriods
  } catch (e) { console.error(e) }
}

const copyJwt = async () => {
  try {
    await navigator.clipboard.writeText(jwtToken.value)
    jwtCopied.value = true
    setTimeout(() => { jwtCopied.value = false }, 2000)
  } catch {}
}

const fetchData = async () => {
  loading.value = true
  error.value = null
  try {
    const [userRes, cvRes, missionsRes] = await Promise.all([
      axios.get(`/auth/${props.userId}`),
      axios.get(`/api/cv/user/${props.userId}`).catch(() => ({ data: { items: [] } })),
      axios.get(`/api/cv/user/${props.userId}/missions`).catch(() => ({ data: { items: [] } })),
      fetchUserTags(),
      fetchPersonalPrompt()
    ])

    user.value = userRes.data
    cvProfile.value = cvRes.data.items?.[0] || cvRes.data || null
    missions.value = missionsRes.data.items || []
    
    if (user.value.unavailability_periods) {
      unavailabilityPeriods.value = [...user.value.unavailability_periods]
    }
  } catch (err) {
    console.error('Failed to fetch dashboard data:', err)
    error.value = "Erreur lors du chargement des données."
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
watch(() => props.userId, fetchData)

const formatDate = (dateStr: string) => {
  if (!dateStr) return ''
  return dateStr // Simplifié pour l'exemple
}
</script>

<template>
  <div class="consultant-dashboard fade-in">
    <!-- Hero Header -->
    <header class="dashboard-hero glass-card">
      <div class="hero-bg-accent"></div>
      
      <div class="hero-main">
        <div class="hero-identity">
          <div class="avatar-wrapper">
            <div class="avatar-glow"></div>
            <img v-if="user?.picture_url" :src="user.picture_url" :alt="user.full_name" class="avatar-img" />
            <div v-else class="avatar-initials">{{ userInitials }}</div>
            <div class="status-badge" :class="{ active: user?.is_active }"></div>
          </div>
          
          <div class="identity-text">
            <div class="name-row">
              <h1>{{ user?.full_name || user?.username }}</h1>
              <span v-if="user?.is_anonymous" class="badge-anon">
                <BrainCircuit size="12" /> Anonyme
              </span>
            </div>
            <div class="meta-row">
              <span class="role-tag"><Briefcase size="14" /> {{ cvProfile?.current_role || user?.role || 'Consultant' }}</span>
              <span v-if="userAgency" class="agency-tag"><MapPin size="14" /> {{ userAgency }}</span>
              <span class="email-tag"><Mail size="14" /> {{ user?.email }}</span>
            </div>
          </div>
        </div>

        <div class="hero-stats">
          <div class="stat-card">
            <span class="stat-label">{{ t('dashboard.stat_experience') }}</span>
            <span class="stat-value">{{ cvProfile?.years_of_experience || '?' }} {{ t('dashboard.unit_years') }}</span>
          </div>
          <div class="stat-card gemini-stat">
            <span class="stat-label">{{ t('dashboard.stat_seniority') }}</span>
            <span class="stat-value">{{ seniorityLevel }}</span>
          </div>
        </div>
      </div>

      <!-- AI Summary Card (In-Hero) -->
      <div v-if="cvProfile?.summary" class="ai-summary-card">
        <div class="ai-header">
          <Sparkles size="16" class="text-gradient-ai" />
          <span class="text-gradient-ai">{{ t('dashboard.ai_summary') }}</span>
        </div>
        <p class="summary-text">{{ cvProfile.summary }}</p>
      </div>

      <!-- Tabs Navigation -->
      <nav class="dashboard-tabs">
        <button 
          v-for="tab in (isOwner ? ['overview', 'experience', 'skills', 'docs', 'settings'] : ['overview', 'experience', 'skills', 'docs'])" 
          :key="tab"
          class="tab-btn"
          :class="{ active: activeTab === tab }"
          @click="activeTab = tab as any"
        >
          <component :is="tab === 'overview' ? Info : tab === 'experience' ? History : tab === 'skills' ? Award : tab === 'settings' ? Settings : FileText" size="16" />
          {{ t(`dashboard.tab_${tab}`) || (tab === 'settings' ? 'Paramètres' : tab.charAt(0).toUpperCase() + tab.slice(1)) }}
        </button>
      </nav>
    </header>

    <!-- Main Content -->
    <main class="dashboard-body">
      <div v-if="loading" class="loading-overlay">
        <div class="spinner"></div>
        <p>Intelligence en cours de chargement...</p>
      </div>

      <div v-else-if="error" class="error-panel glass-card">
        <Info size="32" class="text-red" />
        <p>{{ error }}</p>
        <button @click="fetchData" class="btn-retry">Réessayer</button>
      </div>

      <template v-else>
        <!-- Tab: Overview -->
        <section v-if="activeTab === 'overview'" class="tab-content overview-grid">
          <div class="glass-card info-panel">
            <div class="panel-header">
              <TrendingUp size="18" class="text-primary" />
              <h3>{{ t('dashboard.info_discovered') }}</h3>
            </div>
            <div class="info-list">
              <div class="info-item">
                <span class="label">{{ t('dashboard.main_expertise') }}</span>
                <span class="value">{{ cvProfile?.current_role || t('dashboard.to_be_determined') }}</span>
              </div>
              <div class="info-item">
                <span class="label">{{ t('dashboard.estimated_seniority') }}</span>
                <span class="value">{{ cvProfile?.years_of_experience ? `${cvProfile.years_of_experience} ${t('dashboard.unit_years')}` : t('dashboard.not_available') }}</span>
              </div>
              <div class="info-item">
                <span class="label">{{ t('dashboard.missions_analyzed') }}</span>
                <span class="value">{{ missions.length }}</span>
              </div>
            </div>
          </div>

          <div class="glass-card education-panel">
            <div class="panel-header">
              <GraduationCap size="18" class="text-primary" />
              <h3>{{ t('dashboard.education_title') }}</h3>
            </div>
            <div v-if="cvProfile?.educations?.length" class="edu-list">
              <div v-for="(edu, idx) in cvProfile.educations" :key="idx" class="edu-item">
                <div class="edu-icon"><GraduationCap size="14" /></div>
                <div class="edu-info">
                  <div class="edu-degree">{{ edu.degree }}</div>
                  <div class="edu-school">{{ edu.school }}</div>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">{{ t('dashboard.no_degree') }}</div>
          </div>
        </section>

        <!-- Tab: Experience -->
        <section v-if="activeTab === 'experience'" class="tab-content experience-timeline">
          <div v-if="missions.length" class="timeline-container">
            <div v-for="(mission, idx) in missions" :key="idx" class="mission-card glass-card">
              <div class="mission-header">
                <div class="m-title-row">
                  <h4>{{ mission.title }}</h4>
                  <span class="m-duration">{{ mission.duration || t('dashboard.not_available') }}</span>
                </div>
                <div class="m-company">{{ mission.company || 'Client Zenika' }}</div>
              </div>
              <p class="m-desc">{{ mission.description }}</p>
              <div v-if="mission.competencies?.length" class="m-tech-stack">
                <span v-for="tech in mission.competencies" :key="tech" class="tech-tag">{{ tech }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty-state glass-card">
            <Briefcase size="32" />
            <p>{{ t('dashboard.no_mission') }}</p>
          </div>
        </section>

        <!-- Tab: Skills -->
        <section v-if="activeTab === 'skills'" class="tab-content skills-panel">
          <div class="glass-card">
            <div class="panel-header">
              <Sparkles size="18" class="text-gradient-ai" />
              <h3 class="text-gradient-ai">{{ t('dashboard.ai_scoring_title') }}</h3>
            </div>
            <CompetencyEvaluationPanel :userId="Number(props.userId)" :readonly="props.readonly" />
          </div>
        </section>

        <!-- Tab: Docs -->
        <section v-if="activeTab === 'docs'" class="tab-content docs-grid">
          <div v-if="cvProfile" class="glass-card doc-card">
            <div class="doc-icon"><FileText size="24" /></div>
            <div class="doc-info">
              <div class="doc-name">{{ t('profile.section_cv') }}</div>
              <div class="doc-meta">
                <span class="reliability" :class="{ high: cvProfile.extraction_reliability_score > 80 }">
                  <ShieldCheck size="12" /> {{ t('extractionquality.col_reliability') || 'Fiabilité' }} {{ cvProfile.extraction_reliability_score }}%
                </span>
                <span class="date"><Clock size="12" /> {{ formatDate(cvProfile.updated_at) }}</span>
              </div>
            </div>
            <a :href="cvProfile.source_url" target="_blank" class="doc-link">
              <ExternalLink size="18" />
            </a>
          </div>
          <div v-else class="empty-state glass-card">
            <FileText size="32" />
            <p>{{ t('dashboard.no_doc') }}</p>
        </section>

        <!-- Tab: Settings (Personal Configuration) -->
        <section v-if="activeTab === 'settings' && isOwner" class="tab-content settings-panel">
          <div class="settings-grid">
            <!-- Instructions personnelles -->
            <div class="settings-card glass-card">
              <div class="card-header">
                <MessageSquare size="20" class="text-primary" />
                <h3>Instructions Personnelles</h3>
              </div>
              <p class="card-description">
                Ces instructions personnalisent le comportement de l'Agent IA lorsqu'il interagit avec vous.
              </p>
              <textarea
                v-model="personalPrompt"
                placeholder="Ex : Réponds-moi toujours de façon concise. Mets en avant mes compétences Cloud GCP en priorité..."
                class="settings-textarea"
                rows="5"
              ></textarea>
              <div class="card-footer">
                <button @click="savePersonalPrompt" :disabled="isSavingPrompt" class="btn-primary-ai">
                  <Check v-if="promptSaveSuccess" size="16" />
                  <span>{{ isSavingPrompt ? 'Enregistrement...' : promptSaveSuccess ? 'Sauvegardé !' : 'Sauvegarder' }}</span>
                </button>
                <Transition name="fade-msg">
                  <span v-if="promptSaveError" class="msg-error">Erreur de sauvegarde</span>
                </Transition>
              </div>
            </div>

            <!-- Disponibilités -->
            <div class="settings-card glass-card">
              <div class="card-header">
                <Calendar size="20" class="text-primary" />
                <h3>Gestion des Indisponibilités</h3>
              </div>
              
              <div v-if="unavailabilityPeriods.length" class="availability-list">
                <div v-for="(period, idx) in unavailabilityPeriods" :key="idx" class="availability-item">
                  <div class="item-info">
                    <span class="item-dates"><Clock size="14" /> {{ period.start_date }} → {{ period.end_date }}</span>
                    <div class="item-tags">
                      <span class="tag type">{{ typeLabel[period.type] || period.type }}</span>
                      <span class="tag reason">{{ reasonLabel[period.reason] || period.reason }}</span>
                    </div>
                  </div>
                  <button @click="removeAvailability(idx)" class="btn-remove" aria-label="Supprimer">
                    <XCircle size="18" />
                  </button>
                </div>
              </div>

              <div class="availability-form">
                <div class="form-inputs">
                  <input type="date" v-model="newPeriod.start_date" class="form-input" />
                  <input type="date" v-model="newPeriod.end_date" class="form-input" />
                  <select v-model="newPeriod.type" class="form-input">
                    <option value="full">Journée</option>
                    <option value="am">Matin</option>
                    <option value="pm">Après-midi</option>
                  </select>
                  <button @click="addAvailability" :disabled="!newPeriod.start_date || isSavingAvailability" class="btn-icon-add">
                    <Plus size="20" />
                  </button>
                </div>
              </div>
            </div>

            <!-- Token JWT -->
            <div class="settings-card glass-card full-width">
              <div class="card-header">
                <ShieldCheck size="20" class="text-primary" />
                <h3>Token d'Authentification (JWT)</h3>
                <div class="token-actions">
                  <button @click="jwtVisible = !jwtVisible" class="btn-action-ghost">
                    <EyeOff v-if="jwtVisible" size="16" /> <Eye v-else size="16" />
                  </button>
                  <button @click="copyJwt" class="btn-action-ghost">
                    <Check v-if="jwtCopied" size="16" /> <Copy v-else size="16" />
                  </button>
                </div>
              </div>
              <div class="token-box" :class="{ visible: jwtVisible }">{{ maskedToken }}</div>
            </div>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.consultant-dashboard {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  max-width: 1100px;
  margin: 0 auto;
}

/* Hero Section */
.dashboard-hero {
  position: relative;
  overflow: hidden;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.hero-bg-accent {
  position: absolute;
  top: 0; left: 0; right: 0; height: 100px;
  background: linear-gradient(90deg, var(--zenika-red), var(--gemini-purple));
  opacity: 0.1;
  z-index: 0;
}

.hero-main {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2.5rem 2.5rem 1.5rem;
  gap: 2rem;
  flex-wrap: wrap;
}

.hero-identity {
  display: flex;
  gap: 1.5rem;
  align-items: center;
}

.avatar-wrapper {
  position: relative;
  width: 96px;
  height: 96px;
}

.avatar-glow {
  position: absolute;
  inset: -4px;
  background: var(--gemini-gradient);
  border-radius: 50%;
  opacity: 0.2;
  filter: blur(8px);
}

.avatar-img, .avatar-initials {
  width: 100%; height: 100%;
  border-radius: 50%;
  border: 4px solid white;
  position: relative;
  z-index: 2;
  object-fit: cover;
  box-shadow: var(--shadow-md);
}

.avatar-initials {
  background: #f8f9fa;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  font-weight: 800;
  color: var(--zenika-red);
}

.status-badge {
  position: absolute;
  bottom: 4px; right: 4px;
  width: 18px; height: 18px;
  border-radius: 50%;
  border: 3px solid white;
  background: #cbd5e1;
  z-index: 3;
}
.status-badge.active { background: #10b981; }

.identity-text h1 {
  font-size: 2rem;
  font-weight: 800;
  letter-spacing: -0.5px;
  margin: 0;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}

.badge-anon {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(249, 115, 22, 0.1);
  color: #f97316;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
}

.meta-row {
  display: flex;
/* ... styles existants ... */

.role-tag, .email-tag, .agency-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.9rem;
  color: var(--text-secondary);
  font-weight: 600;
}

}

.stat-card {
  background: rgba(255, 255, 255, 0.5);
  padding: 0.75rem 1.25rem;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  min-width: 100px;
  border: 1px solid rgba(255, 255, 255, 0.8);
}

.gemini-stat {
  border-color: rgba(142, 117, 255, 0.3);
  background: rgba(142, 117, 255, 0.05);
}

.stat-label {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-secondary);
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: 1.1rem;
  font-weight: 800;
  color: var(--text-primary);
}

/* AI Summary */
.ai-summary-card {
  margin: 0 2.5rem 1.5rem;
  padding: 1.25rem;
  background: rgba(142, 117, 255, 0.03);
  border-radius: 16px;
  border: 1px dashed rgba(142, 117, 255, 0.3);
}

.ai-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.summary-text {
  font-size: 0.95rem;
  line-height: 1.6;
  color: var(--text-primary);
  font-style: italic;
}

/* Tabs */
.dashboard-tabs {
  display: flex;
  padding: 0 2.5rem;
  border-top: 1px solid rgba(0,0,0,0.05);
  gap: 2rem;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 1.25rem 0;
  background: none;
  border: none;
  border-bottom: 3px solid transparent;
  font-weight: 700;
  font-size: 0.9rem;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: var(--zenika-red);
}

.tab-btn.active {
  color: var(--zenika-red);
  border-bottom-color: var(--zenika-red);
}

/* Body & Content */
.dashboard-body {
  position: relative;
  min-height: 300px;
}

.tab-content {
  animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 1.5rem;
}

.panel-header h3 {
  font-size: 1.1rem;
  font-weight: 800;
  margin: 0;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.info-item {
  display: flex;
  justify-content: space-between;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid rgba(0,0,0,0.03);
}

.info-item .label {
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.info-item .value {
  font-weight: 700;
  color: var(--text-primary);
}

.edu-list {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.edu-item {
  display: flex;
  gap: 12px;
}

.edu-icon {
  width: 36px; height: 36px;
  border-radius: 10px;
  background: rgba(227, 25, 55, 0.05);
  color: var(--zenika-red);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.edu-degree { font-weight: 700; font-size: 0.95rem; }
.edu-school { font-size: 0.85rem; color: var(--text-secondary); }

/* Experience Timeline */
.experience-timeline {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.timeline-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.mission-card {
  padding: 1.5rem;
}

.mission-header {
  margin-bottom: 1rem;
}

.m-title-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.m-title-row h4 {
  font-size: 1.1rem;
  font-weight: 800;
  color: var(--text-primary);
  margin: 0;
}

.m-duration {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--text-secondary);
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 6px;
}

.m-company {
  font-weight: 700;
  color: var(--zenika-red);
  font-size: 0.9rem;
  margin-top: 2px;
}

.m-desc {
  font-size: 0.95rem;
  line-height: 1.6;
  color: var(--text-secondary);
  margin-bottom: 1.25rem;
}

.m-tech-stack {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tech-tag {
  background: white;
  border: 1px solid rgba(0,0,0,0.06);
  padding: 4px 10px;
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
}

/* Documents */
.doc-card {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 1.5rem;
}

.doc-icon {
  width: 52px; height: 52px;
  border-radius: 14px;
  background: rgba(142, 117, 255, 0.1);
  color: var(--gemini-purple);
  display: flex;
  align-items: center;
  justify-content: center;
}

.doc-info { flex: 1; }
.doc-name { font-weight: 800; font-size: 1rem; margin-bottom: 4px; }
.doc-meta { display: flex; gap: 16px; font-size: 0.8rem; }

.reliability {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 700;
  color: #f59e0b;
}
.reliability.high { color: #10b981; }

.doc-link {
  width: 44px; height: 44px;
  border-radius: 12px;
  background: #f8f9fa;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.doc-link:hover {
  background: var(--zenika-red);
  color: white;
  transform: scale(1.1);
}

/* Utility */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem;
  text-align: center;
  color: var(--text-secondary);
  gap: 1rem;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.loading-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  gap: 1.5rem;
}

.spinner {
  width: 40px; height: 40px;
  border: 4px solid rgba(0,0,0,0.05);
  border-top-color: var(--gemini-purple);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Settings Tab Styles */
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

.settings-card {
  padding: 1.75rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.settings-card.full-width {
  grid-column: 1 / -1;
}

.settings-card h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 800;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-primary);
}

.card-description {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin: -0.5rem 0 0.5rem;
}

.settings-textarea {
  width: 100%;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.1);
  padding: 1rem;
  font-family: inherit;
  font-size: 0.95rem;
  resize: vertical;
  background: rgba(255,255,255,0.5);
}

.settings-textarea:focus {
  outline: none;
  border-color: var(--gemini-purple);
  box-shadow: 0 0 0 3px rgba(142, 117, 255, 0.1);
}

.btn-primary-ai {
  background: var(--gemini-gradient);
  color: white;
  border: none;
  padding: 0.6rem 1.2rem;
  border-radius: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary-ai:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(142, 117, 255, 0.2);
}

.availability-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.availability-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: rgba(255,255,255,0.4);
  border: 1px solid rgba(0,0,0,0.05);
  border-radius: 12px;
}

.item-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item-dates {
  font-size: 0.9rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 6px;
}

.item-tags {
  display: flex;
  gap: 6px;
}

.tag {
  font-size: 0.75rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 20px;
}

.tag.type { background: #e0f2fe; color: #0369a1; }
.tag.reason { background: #fef3c7; color: #b45309; }

.btn-remove {
  background: none;
  border: none;
  color: #fca5a5;
  cursor: pointer;
  transition: color 0.2s;
}

.btn-remove:hover { color: #ef4444; }

.availability-form {
  margin-top: 0.5rem;
}

.form-inputs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.form-input {
  flex: 1;
  min-width: 100px;
  padding: 0.6rem;
  border-radius: 8px;
  border: 1px solid rgba(0,0,0,0.1);
}

.btn-icon-add {
  background: var(--zenika-red);
  color: white;
  border: none;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.token-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.btn-action-ghost {
  background: rgba(0,0,0,0.03);
  border: 1px solid rgba(0,0,0,0.08);
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary);
}

.token-box {
  background: #1e293b;
  color: #94a3b8;
  padding: 1.25rem;
  border-radius: 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  word-break: break-all;
  filter: blur(4px);
  transition: all 0.3s;
}

.token-box.visible {
  filter: none;
  color: #10b981;
}

@media (max-width: 768px) {
  .settings-grid { grid-template-columns: 1fr; }
  .form-inputs { flex-direction: column; }
  .btn-icon-add { width: 100%; }
}
</style>
