<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { authService } from '../services/auth'
import {
  User as UserIcon,
  Mail,
  Hash,
  ShieldCheck,
  ChevronRight,
  AlertCircle,
  Fingerprint,
  MessageSquare,
  Calendar,
  XCircle,
  Plus,
  Award,
  Eye,
  EyeOff,
  Copy,
  Check,
  Clock,
  Briefcase,
  FileText
} from 'lucide-vue-next'
import axios from 'axios'
import CompetencyEvaluationPanel from '../components/CompetencyEvaluationPanel.vue'

// ── Types ──────────────────────────────────────────────────────────────────
interface Category { id: number; name: string; description: string }

// ── State ──────────────────────────────────────────────────────────────────
const activeTab = ref<'identity' | 'competencies' | 'settings'>('identity')

const categories = ref<Category[]>([])
const isLoadingCategories = ref(true)
const error = ref<string | null>(null)

const user = authService.state.user
const jwtToken = ref(localStorage.getItem('access_token') || '')
const jwtVisible = ref(false)
const jwtCopied = ref(false)

const personalPrompt = ref('')
const isSavingPrompt = ref(false)
const promptSaveSuccess = ref(false)
const promptSaveError = ref(false)

const unavailabilityPeriods = ref<any[]>([])
const newPeriod = ref({ start_date: '', end_date: '', type: 'full', reason: 'client' })
const isSavingAvailability = ref(false)

const cvUrl = ref('')
const isImportingCv = ref(false)
const cvImportSuccess = ref(false)
const cvImportError = ref<string | null>(null)

// ── Computed ───────────────────────────────────────────────────────────────
const userInitials = computed(() => {
  const name = user?.full_name || user?.username || ''
  return name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
})

const userRole = computed(() => {
  const roleMap: Record<string, string> = {
    admin: 'Administrateur',
    rh: 'Ressources Humaines',
    commercial: 'Commercial',
    consultant: 'Consultant',
  }
  return roleMap[user?.role ?? ''] ?? user?.role ?? 'Utilisateur'
})

const maskedToken = computed(() => {
  if (!jwtToken.value) return 'Token introuvable'
  if (jwtVisible.value) return jwtToken.value
  return jwtToken.value.slice(0, 20) + '••••••••••••••••••••' + jwtToken.value.slice(-10)
})

// ── Actions ────────────────────────────────────────────────────────────────
const fetchCategories = async () => {
  try {
    const response = await axios.get('/api/items/categories')
    categories.value = response.data.items || []
  } catch (err) {
    error.value = "Impossible de récupérer les catégories."
  } finally {
    isLoadingCategories.value = false
  }
}

const getCategoryName = (id: number) => {
  const cat = categories.value.find(c => c.id === id)
  return cat ? cat.name : `Catégorie #${id}`
}

const copyJwt = async () => {
  try {
    await navigator.clipboard.writeText(jwtToken.value)
    jwtCopied.value = true
    setTimeout(() => { jwtCopied.value = false }, 2000)
  } catch {}
}

const fetchPersonalPrompt = async () => {
  try {
    const token = localStorage.getItem('access_token')
    const response = await axios.get('/api/prompts/user/me', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    personalPrompt.value = response.data.value || ''
  } catch {}
}

const savePersonalPrompt = async () => {
  isSavingPrompt.value = true
  promptSaveSuccess.value = false
  promptSaveError.value = false
  try {
    const token = localStorage.getItem('access_token')
    await axios.put('/api/prompts/user/me', { value: personalPrompt.value }, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    promptSaveSuccess.value = true
    setTimeout(() => { promptSaveSuccess.value = false }, 3000)
  } catch {
    promptSaveError.value = true
    setTimeout(() => { promptSaveError.value = false }, 3000)
  } finally {
    isSavingPrompt.value = false
  }
}

const loadAvailability = () => {
  if (user?.unavailability_periods) {
    unavailabilityPeriods.value = [...user.unavailability_periods]
  }
}

const addAvailability = async () => {
  if (!newPeriod.value.start_date || !newPeriod.value.end_date) return
  const updatedPeriods = [...unavailabilityPeriods.value, { ...newPeriod.value }]
  isSavingAvailability.value = true
  try {
    const token = localStorage.getItem('access_token')
    await axios.put(`/api/users/${user?.id}`, { unavailability_periods: updatedPeriods }, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
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
    const token = localStorage.getItem('access_token')
    await axios.put(`/api/users/${user?.id}`, { unavailability_periods: updatedPeriods }, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    unavailabilityPeriods.value = updatedPeriods
  } catch (e) { console.error(e) }
}

const reasonLabel: Record<string, string> = {
  client: '💼 Client', vacances: '🏖️ Vacances', formation: '📚 Formation'
}
const typeLabel: Record<string, string> = {
  full: 'Journée', am: 'Matin', pm: 'Après-midi'
}

const importCv = async () => {
  if (!cvUrl.value) return
  isImportingCv.value = true
  cvImportSuccess.value = false
  cvImportError.value = null
  try {
    const token = localStorage.getItem('access_token')
    const folderName = `${user?.first_name || ''} ${user?.last_name || ''}`.trim() || user?.username || 'Unknown'
    await axios.post('/api/cvs/import', { 
      url: cvUrl.value,
      folder_name: folderName
    }, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    cvImportSuccess.value = true
    cvUrl.value = ''
    setTimeout(() => { cvImportSuccess.value = false }, 3000)
  } catch (err: any) {
    cvImportError.value = err.response?.data?.detail || "Erreur lors de l'importation"
  } finally {
    isImportingCv.value = false
  }
}

onMounted(() => {
  fetchCategories()
  fetchPersonalPrompt()
  loadAvailability()
})
</script>

<template>
  <div class="profile-page fade-in">

    <!-- ── Hero Card ────────────────────────────────────────────────────── -->
    <div class="hero-card">
      <div class="hero-bg-pattern" aria-hidden="true"></div>

      <div class="hero-content">
        <!-- Avatar -->
        <div class="avatar-ring">
          <img v-if="user?.picture_url" :src="user.picture_url" :alt="user.full_name" class="avatar-img" />
          <div v-else class="avatar-initials">{{ userInitials }}</div>
          <div class="avatar-status" :class="user?.is_active ? 'active' : 'inactive'" />
        </div>

        <!-- Identity -->
        <div class="hero-identity">
          <h1>{{ user?.full_name || user?.username }}</h1>
          <div class="hero-meta">
            <span class="hero-role">{{ userRole }}</span>
            <span class="hero-sep">·</span>
            <span class="hero-email"><Mail :size="13" /> {{ user?.email }}</span>
          </div>
        </div>

        <!-- Status badges -->
        <div class="hero-badges">
          <span class="badge-status" :class="user?.is_active ? 'active' : 'inactive'">
            <ShieldCheck :size="13" />
            {{ user?.is_active ? 'Actif' : 'Inactif' }}
          </span>
          <span class="badge-id">
            <Hash :size="12" /> #{{ user?.id }}
          </span>
        </div>
      </div>

      <!-- Tabs -->
      <nav class="hero-tabs" role="tablist" aria-label="Sections du profil">
        <button
          role="tab"
          :aria-selected="activeTab === 'identity'"
          class="tab-btn" :class="{ active: activeTab === 'identity' }"
          @click="activeTab = 'identity'"
          id="tab-identity"
          aria-controls="panel-identity"
        >
          <UserIcon :size="15" />
          Mon Profil
        </button>
        <button
          role="tab"
          :aria-selected="activeTab === 'competencies'"
          class="tab-btn" :class="{ active: activeTab === 'competencies' }"
          @click="activeTab = 'competencies'"
          id="tab-competencies"
          aria-controls="panel-competencies"
        >
          <Award :size="15" />
          Mes Compétences
        </button>
        <button
          role="tab"
          :aria-selected="activeTab === 'settings'"
          class="tab-btn" :class="{ active: activeTab === 'settings' }"
          @click="activeTab = 'settings'"
          id="tab-settings"
          aria-controls="panel-settings"
        >
          <MessageSquare :size="15" />
          Paramètres Agent
        </button>
      </nav>
    </div>

    <!-- ── Tab Panels ───────────────────────────────────────────────────── -->

    <!-- ① Mon Profil -->
    <div v-show="activeTab === 'identity'" id="panel-identity" role="tabpanel" aria-labelledby="tab-identity" class="tab-panel">
      <div class="two-col-grid">

        <!-- Informations -->
        <div class="panel-card">
          <div class="panel-card-header">
            <UserIcon :size="18" class="card-icon" />
            <h2>Informations</h2>
          </div>
          <div class="info-list">
            <div class="info-row">
              <div class="info-icon-wrap"><Fingerprint :size="15" /></div>
              <div>
                <p class="info-label">Identifiant</p>
                <p class="info-value">{{ user?.username }}</p>
              </div>
            </div>
            <div class="info-row">
              <div class="info-icon-wrap"><Mail :size="15" /></div>
              <div>
                <p class="info-label">Email</p>
                <p class="info-value">{{ user?.email }}</p>
              </div>
            </div>
            <div class="info-row">
              <div class="info-icon-wrap"><Briefcase :size="15" /></div>
              <div>
                <p class="info-label">Rôle</p>
                <p class="info-value">{{ userRole }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Autorisations -->
        <div class="panel-card">
          <div class="panel-card-header">
            <ShieldCheck :size="18" class="card-icon" />
            <h2>Autorisations</h2>
          </div>
          <p class="card-desc">Catégories d'objets accessibles dans la plateforme.</p>
          <div v-if="isLoadingCategories" class="mini-loader">
            <div class="spinner-sm" /><span>Chargement...</span>
          </div>
          <div v-else-if="user?.allowed_category_ids?.length" class="tags-wrap">
            <span v-for="id in user.allowed_category_ids" :key="id" class="access-tag">
              <ChevronRight :size="12" /> {{ getCategoryName(id) }}
            </span>
          </div>
          <div v-else class="empty-mini">
            <AlertCircle :size="20" />
            <p>Aucune catégorie assignée</p>
          </div>
        </div>

        <!-- Mon CV -->
        <div class="panel-card full-width">
          <div class="panel-card-header">
            <FileText :size="18" class="card-icon" />
            <h2>Mon Curriculum Vitae</h2>
          </div>
          <p class="card-desc">Rattachez votre CV via une URL Google Docs. Cela permettra à l'Agent RH d'extraire vos compétences et missions.</p>
          
          <div class="add-period-form" style="margin-top: 1rem;">
            <p class="form-label">Importer depuis Google Docs</p>
            <div class="form-row" style="align-items: flex-start;">
              <label class="field" style="flex: 1;">
                <input 
                  type="url" 
                  v-model="cvUrl" 
                  class="field-input" 
                  placeholder="https://docs.google.com/document/d/1X..." 
                  aria-label="URL du Google Doc" 
                />
              </label>
              <button @click="importCv" :disabled="!cvUrl || isImportingCv" class="btn-primary" style="padding: 9px 18px; margin-top: 0;">
                <Check v-if="cvImportSuccess" :size="16" />
                <Plus v-else :size="16" />
                <span>{{ isImportingCv ? 'Importation...' : cvImportSuccess ? 'Importé !' : 'Importer le CV' }}</span>
              </button>
            </div>
            <Transition name="fade-msg">
              <div v-if="cvImportError" class="msg-error" style="margin-top: 8px;">
                <AlertCircle :size="14" style="display:inline; margin-right:4px;" />
                {{ cvImportError }}
              </div>
            </Transition>
          </div>
        </div>

        <!-- Indisponibilités — pleine largeur -->
        <div class="panel-card full-width">
          <div class="panel-card-header">
            <Calendar :size="18" class="card-icon" />
            <h2>Indisponibilités</h2>
          </div>
          <p class="card-desc">Déclarez vos périodes d'absence (congés, mission client, formation).</p>

          <!-- Liste existante -->
          <div v-if="unavailabilityPeriods.length" class="periods-list">
            <div v-for="(period, idx) in unavailabilityPeriods" :key="idx" class="period-chip">
              <div class="period-chip-left">
                <span class="period-dates">
                  <Clock :size="13" />
                  {{ period.start_date }} → {{ period.end_date }}
                </span>
                <div class="period-tags">
                  <span class="ptag type">{{ typeLabel[period.type] ?? period.type }}</span>
                  <span class="ptag reason">{{ reasonLabel[period.reason] ?? period.reason }}</span>
                </div>
              </div>
              <button @click="removeAvailability(idx)" class="remove-btn" :aria-label="`Supprimer la période ${period.start_date}`">
                <XCircle :size="17" />
              </button>
            </div>
          </div>
          <div v-else class="empty-mini" style="margin-bottom: 1.25rem;">
            <Calendar :size="20" /><p>Aucune indisponibilité déclarée</p>
          </div>

          <!-- Formulaire ajout -->
          <div class="add-period-form">
            <p class="form-label">Ajouter une période</p>
            <div class="form-row">
              <label class="field">
                <span>Début</span>
                <input type="date" v-model="newPeriod.start_date" class="field-input" aria-label="Date de début" />
              </label>
              <label class="field">
                <span>Fin</span>
                <input type="date" v-model="newPeriod.end_date" class="field-input" aria-label="Date de fin" />
              </label>
              <label class="field">
                <span>Type</span>
                <select v-model="newPeriod.type" class="field-input" aria-label="Type d'indisponibilité">
                  <option value="full">Journée complète</option>
                  <option value="am">Matin</option>
                  <option value="pm">Après-midi</option>
                </select>
              </label>
              <label class="field">
                <span>Motif</span>
                <select v-model="newPeriod.reason" class="field-input" aria-label="Motif">
                  <option value="client">Client</option>
                  <option value="vacances">Vacances</option>
                  <option value="formation">Formation</option>
                </select>
              </label>
              <button @click="addAvailability" :disabled="!newPeriod.start_date || !newPeriod.end_date || isSavingAvailability" class="btn-add" aria-label="Ajouter la période">
                <Plus :size="16" />
                <span>Ajouter</span>
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- ② Mes Compétences -->
    <div v-show="activeTab === 'competencies'" id="panel-competencies" role="tabpanel" aria-labelledby="tab-competencies" class="tab-panel">
      <div class="panel-card" v-if="user?.id">
        <div class="panel-card-header">
          <Award :size="18" class="card-icon" />
          <h2>Évaluation de mes compétences</h2>
        </div>
        <p class="card-desc">
          Auto-évaluez chaque compétence extraite de votre CV. La note 🤖 Gemini est calculée automatiquement sur vos missions réelles — elle ne ment pas.
        </p>
        <CompetencyEvaluationPanel :userId="user.id" :readonly="false" />
      </div>
    </div>

    <!-- ③ Paramètres Agent -->
    <div v-show="activeTab === 'settings'" id="panel-settings" role="tabpanel" aria-labelledby="tab-settings" class="tab-panel">
      <div class="two-col-grid">

        <!-- Instructions personnelles -->
        <div class="panel-card full-width">
          <div class="panel-card-header">
            <MessageSquare :size="18" class="card-icon" />
            <h2>Instructions Personnelles</h2>
          </div>
          <p class="card-desc">
            Ces instructions sont injectées dans le contexte de l'Agent lorsque vous interagissez avec lui. Utilisez-les pour personnaliser son comportement.
          </p>
          <textarea
            v-model="personalPrompt"
            placeholder="Ex : Réponds-moi toujours de façon concise. Mets en avant mes compétences Cloud GCP en priorité..."
            class="prompt-textarea"
            rows="7"
            aria-label="Instructions personnelles pour l'agent"
          ></textarea>
          <div class="prompt-actions">
            <button @click="savePersonalPrompt" :disabled="isSavingPrompt" class="btn-primary" aria-label="Sauvegarder les instructions">
              <Check v-if="promptSaveSuccess" :size="15" />
              <span>{{ isSavingPrompt ? 'Enregistrement...' : promptSaveSuccess ? 'Sauvegardé !' : 'Sauvegarder' }}</span>
            </button>
            <Transition name="fade-msg">
              <span v-if="promptSaveError" class="msg-error">Erreur lors de la sauvegarde</span>
            </Transition>
          </div>
        </div>

        <!-- JWT Token -->
        <div class="panel-card full-width">
          <div class="panel-card-header">
            <ShieldCheck :size="18" class="card-icon token-icon" />
            <h2>Token d'Authentification</h2>
            <div class="jwt-actions-header">
              <button @click="jwtVisible = !jwtVisible" class="btn-ghost-sm" :aria-label="jwtVisible ? 'Masquer le token' : 'Révéler le token'">
                <EyeOff v-if="jwtVisible" :size="14" /> <Eye v-else :size="14" />
                {{ jwtVisible ? 'Masquer' : 'Révéler' }}
              </button>
              <button @click="copyJwt" class="btn-ghost-sm" aria-label="Copier le token">
                <Check v-if="jwtCopied" :size="14" class="text-green" /> <Copy v-else :size="14" />
                {{ jwtCopied ? 'Copié !' : 'Copier' }}
              </button>
            </div>
          </div>
          <p class="card-desc">Ce jeton cryptographique est votre identifiant de session actif.</p>
          <div class="jwt-box" :class="{ revealed: jwtVisible }">{{ maskedToken }}</div>
        </div>

      </div>
    </div>

  </div>
</template>

<style scoped>
/* ── Page layout ────────────────────────────────────────────────────────── */
.profile-page {
  max-width: 1040px;
  margin: 0 auto;
  padding: 2rem 1.5rem 4rem;
}

.fade-in { animation: fadeIn 0.4s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

/* ── Hero Card ──────────────────────────────────────────────────────────── */
.hero-card {
  position: relative;
  background: white;
  border-radius: 24px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.06);
  border: 1px solid #f0f0f0;
  overflow: hidden;
  margin-bottom: 1.75rem;
}

.hero-bg-pattern {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(227,25,55,0.04) 0%, rgba(227,25,55,0.01) 50%, transparent 100%);
  pointer-events: none;
}

.hero-content {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 2rem 2rem 1.5rem;
  flex-wrap: wrap;
}

/* Avatar */
.avatar-ring {
  position: relative;
  flex-shrink: 0;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: linear-gradient(135deg, #E31937 0%, #c01228 100%);
  padding: 3px;
  box-shadow: 0 6px 20px rgba(227,25,55,0.25);
}

.avatar-img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
  border: 3px solid white;
}

.avatar-initials {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.6rem;
  font-weight: 800;
  color: #E31937;
  letter-spacing: -1px;
}

.avatar-status {
  position: absolute;
  bottom: 3px;
  right: 3px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 3px solid white;
}
.avatar-status.active { background: #22c55e; }
.avatar-status.inactive { background: #94a3b8; }

/* Identity */
.hero-identity { flex: 1; min-width: 180px; }
.hero-identity h1 {
  font-size: 1.75rem;
  font-weight: 800;
  color: #111;
  letter-spacing: -0.5px;
  margin: 0 0 0.35rem;
}
.hero-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.hero-role {
  font-size: 0.9rem;
  font-weight: 600;
  color: #E31937;
}
.hero-sep { color: #d1d5db; }
.hero-email {
  font-size: 0.85rem;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Badges */
.hero-badges { display: flex; gap: 0.5rem; flex-wrap: wrap; align-self: flex-start; }
.badge-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 700;
}
.badge-status.active { background: #dcfce7; color: #16a34a; }
.badge-status.inactive { background: #f1f5f9; color: #64748b; }
.badge-id {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 700;
  font-family: monospace;
  background: rgba(227,25,55,0.06);
  color: #E31937;
}

/* ── Tabs ───────────────────────────────────────────────────────────────── */
.hero-tabs {
  display: flex;
  border-top: 1px solid #f3f4f6;
  padding: 0 1.5rem;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 1rem 1.25rem;
  border: none;
  background: none;
  font-size: 0.88rem;
  font-weight: 600;
  color: #6b7280;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.2s;
}
.tab-btn:hover { color: #E31937; }
.tab-btn.active {
  color: #E31937;
  border-bottom-color: #E31937;
}

/* ── Tab panels ─────────────────────────────────────────────────────────── */
.tab-panel { animation: fadeIn 0.25s ease-out; }

.two-col-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
}
@media (max-width: 768px) { .two-col-grid { grid-template-columns: 1fr; } }

.full-width { grid-column: 1 / -1; }

/* ── Panel cards ────────────────────────────────────────────────────────── */
.panel-card {
  background: white;
  border-radius: 20px;
  padding: 1.75rem;
  border: 1px solid #f0f0f0;
  box-shadow: 0 4px 20px rgba(0,0,0,0.03);
  transition: box-shadow 0.2s;
}
.panel-card:hover { box-shadow: 0 6px 28px rgba(0,0,0,0.06); }

.panel-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 1.25rem;
}
.panel-card-header h2 {
  font-size: 1rem;
  font-weight: 700;
  color: #111;
  margin: 0;
  flex: 1;
}
.card-icon { color: #E31937; flex-shrink: 0; }
.card-desc {
  font-size: 0.85rem;
  color: #6b7280;
  margin: -0.5rem 0 1.25rem;
  line-height: 1.6;
}

/* ── Info list ──────────────────────────────────────────────────────────── */
.info-list { display: flex; flex-direction: column; gap: 1rem; }
.info-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 0.75rem;
  background: #fafafa;
  border-radius: 12px;
  border: 1px solid #f3f4f6;
}
.info-icon-wrap {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(227,25,55,0.07);
  color: #E31937;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.info-label {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #9ca3af;
  margin: 0 0 2px;
}
.info-value {
  font-size: 0.95rem;
  font-weight: 600;
  color: #111;
  margin: 0;
}

/* ── Tags ───────────────────────────────────────────────────────────────── */
.tags-wrap { display: flex; flex-wrap: wrap; gap: 8px; }
.access-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  background: #f8f9fa;
  border: 1.5px solid #e5e7eb;
  border-radius: 20px;
  font-size: 0.82rem;
  font-weight: 600;
  color: #374151;
  transition: all 0.15s;
}
.access-tag:hover { border-color: #E31937; color: #E31937; background: #fff5f5; }

/* ── Periods ────────────────────────────────────────────────────────────── */
.periods-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 1.25rem; }
.period-chip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 12px;
  transition: border-color 0.2s;
}
.period-chip:hover { border-color: #fca5a5; }
.period-chip-left { display: flex; flex-direction: column; gap: 5px; }
.period-dates {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.88rem;
  font-weight: 600;
  color: #374151;
}
.period-tags { display: flex; gap: 6px; }
.ptag {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 20px;
  text-transform: uppercase;
}
.ptag.type { background: #dbeafe; color: #1d4ed8; }
.ptag.reason { background: #fef9c3; color: #854d0e; }
.remove-btn {
  background: none;
  border: none;
  color: #fca5a5;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  transition: color 0.15s;
  display: flex;
}
.remove-btn:hover { color: #ef4444; }

/* ── Add Period Form ────────────────────────────────────────────────────── */
.add-period-form {
  background: #fafafa;
  border: 1.5px dashed #e5e7eb;
  border-radius: 14px;
  padding: 1rem 1.25rem;
}
.form-label {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #9ca3af;
  margin: 0 0 0.75rem;
}
.form-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: flex-end;
}
.field { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 110px; }
.field > span { font-size: 0.75rem; font-weight: 600; color: #6b7280; }
.field-input {
  padding: 7px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 0.85rem;
  font-family: inherit;
  background: white;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  width: 100%;
}
.field-input:focus { border-color: #E31937; box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.25); }

.btn-add {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #E31937;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  height: fit-content;
}
.btn-add:hover:not(:disabled) { background: #c01228; transform: translateY(-1px); }
.btn-add:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Prompt ─────────────────────────────────────────────────────────────── */
.prompt-textarea {
  width: 100%;
  padding: 1rem;
  border: 1.5px solid #e5e7eb;
  border-radius: 12px;
  font-family: inherit;
  font-size: 0.9rem;
  line-height: 1.7;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  margin-bottom: 1rem;
  box-sizing: border-box;
}
.prompt-textarea:focus { border-color: #E31937; box-shadow: 0 0 0 3px rgba(227,25,55,0.25); }

.prompt-actions { display: flex; align-items: center; gap: 1rem; }

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 22px;
  background: #E31937;
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-primary:hover:not(:disabled) { background: #c01228; transform: translateY(-1px); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

.msg-error { color: #dc2626; font-size: 0.85rem; font-weight: 500; }

/* ── JWT ────────────────────────────────────────────────────────────────── */
.token-icon { color: #7c3aed !important; }

.jwt-actions-header { display: flex; gap: 8px; margin-left: auto; }
.btn-ghost-sm {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: white;
  font-size: 0.78rem;
  font-weight: 600;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-ghost-sm:hover { border-color: #E31937; color: #E31937; }

.jwt-box {
  background: #0f172a;
  color: #94a3b8;
  padding: 1rem 1.25rem;
  border-radius: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  word-break: break-all;
  line-height: 1.6;
  border: 1px solid rgba(255,255,255,0.05);
  filter: blur(3px);
  transition: filter 0.3s;
  user-select: none;
}
.jwt-box.revealed {
  color: #4ade80;
  filter: none;
  user-select: text;
}

.text-green { color: #22c55e; }

/* ── Misc ───────────────────────────────────────────────────────────────── */
.mini-loader { display: flex; align-items: center; gap: 8px; color: #9ca3af; font-size: 0.85rem; }
.spinner-sm {
  width: 16px; height: 16px;
  border: 2px solid #e5e7eb;
  border-top-color: #E31937;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.empty-mini { display: flex; align-items: center; gap: 8px; color: #9ca3af; font-size: 0.85rem; }
.empty-mini p { margin: 0; }

.fade-msg-enter-active, .fade-msg-leave-active { transition: opacity 0.3s; }
.fade-msg-enter-from, .fade-msg-leave-to { opacity: 0; }
</style>
