<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import { Briefcase, ChevronLeft, ArrowRight, Loader2, User as UserIcon, Users, Calendar, CheckCircle2, Clock, AlertTriangle, Target, History, ChevronDown, XCircle, Send, Trophy, TrendingDown, Ban, FileText } from 'lucide-vue-next'
import { useHead } from '@vueuse/head'
import { useRouter } from 'vue-router'
import ConsultantProfile from '@/components/ConsultantProfile.vue'
import { authService } from '@/services/auth'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const isNew = computed(() => props.id === 'new')

const mission = ref<any>(null)
const loading = ref(false)

const draftTitle = ref('')
const draftDescription = ref('')
const draftUrl = ref('')
const draftFile = ref<File | null>(null)
const selectedUserId = ref<number | null>(null)

const handleFileUpload = (event: any) => {
  const file = event.target.files[0]
  if (file) {
    draftFile.value = file
  }
}

useHead({ title: isNew.value ? 'Nouvelle Mission - Zenika' : 'Détail Mission - Zenika' })

const fetchMission = async () => {
  if (isNew.value) return
  loading.value = true
  try {
    const response = await axios.get(`/api/missions/missions/${props.id}`)
    mission.value = response.data
  } catch (error) {
    console.error('Erreur chargement mission:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchMission()
})

const pollingTask = ref(false)
const pollCounter = ref(0)
const maxPolls = 60 // 2 minutes

const pollMissionStatus = async (taskId: string) => {
  if (pollCounter.value > maxPolls) {
    alert("Délai d'attente dépassé.")
    loading.value = false
    pollingTask.value = false
    return
  }
  
  try {
    const res = await axios.get(`/api/missions/missions/task/${taskId}`)
    if (res.data.status === 'completed' && res.data.mission_id) {
      const realRes = await axios.get(`/api/missions/missions/${res.data.mission_id}`)
      mission.value = realRes.data
      router.replace(`/missions/${mission.value.id}`)
      loading.value = false
      pollingTask.value = false
    } else if (res.data.status === 'failed') {
      alert("Erreur de l'agent: " + res.data.error)
      loading.value = false
      pollingTask.value = false
    } else {
      pollCounter.value++
      setTimeout(() => pollMissionStatus(taskId), 2000)
    }
  } catch (err) {
    pollCounter.value++
    setTimeout(() => pollMissionStatus(taskId), 2000)
  }
}

const analyzeMission = async () => {
  if (!draftTitle.value) return
  if (!draftDescription.value && !draftUrl.value && !draftFile.value) {
    alert("Veuillez fournir au moins une description, une URL ou un fichier.")
    return
  }
  
  loading.value = true
  pollingTask.value = true
  pollCounter.value = 0
  
  const formData = new FormData()
  formData.append('title', draftTitle.value)
  if (draftDescription.value) formData.append('description', draftDescription.value)
  if (draftUrl.value) formData.append('url', draftUrl.value)
  if (draftFile.value) formData.append('file', draftFile.value)
  
  try {
    const response = await axios.post('/api/missions/missions', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    if (response.data.task_id) {
      pollMissionStatus(response.data.task_id)
    } else {
      mission.value = response.data
      router.replace(`/missions/${mission.value.id}`)
      loading.value = false
      pollingTask.value = false
    }
  } catch (error) {
    console.error('Erreur analyse:', error)
    alert("Impossible de soumettre la mission (Erreur serveur)")
    loading.value = false
    pollingTask.value = false
  }
}

const reanalyzeMission = async () => {
  if (isNew.value || !mission.value) return
  
  const confirmReanalyze = confirm("Voulez-vous vraiment relancer l'analyse et l'affectation IA pour cette mission (cela écrasera l'équipe actuelle) ?")
  if (!confirmReanalyze) return
  
  loading.value = true
  pollingTask.value = true
  pollCounter.value = 0
  
  try {
    const response = await axios.post(`/api/missions/missions/${mission.value.id}/reanalyze`)
    
    if (response.data.task_id) {
      pollMissionStatus(response.data.task_id)
    }
  } catch (error) {
    console.error('Erreur ré-analyse:', error)
    alert("Impossible de relancer l'analyse (Erreur serveur)")
    loading.value = false
    pollingTask.value = false
  }
}

const getRoleColor = (role: string) => {
  if (role.includes('Directeur')) return 'role-dp'
  if (role.includes('Tech Lead') || role.includes('Lead')) return 'role-lead'
  return 'role-dev'
}

// ─── Status Management ────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; cssClass: string; icon: string }> = {
  DRAFT:                { label: 'Brouillon',          cssClass: 'status-draft',      icon: 'FileText' },
  ANALYSIS_IN_PROGRESS: { label: 'Analyse en cours',   cssClass: 'status-analysis',   icon: 'Loader2' },
  STAFFED:              { label: 'Équipe proposée',     cssClass: 'status-staffed',    icon: 'CheckCircle2' },
  NO_GO:                { label: 'No-Go',               cssClass: 'status-nogo',       icon: 'XCircle' },
  SUBMITTED_TO_CLIENT:  { label: 'Soumis au client',    cssClass: 'status-submitted',  icon: 'Send' },
  WON:                  { label: 'Gagné 🏆',            cssClass: 'status-won',        icon: 'Trophy' },
  LOST:                 { label: 'Perdu',               cssClass: 'status-lost',       icon: 'TrendingDown' },
  CANCELLED:            { label: 'Annulé',              cssClass: 'status-cancelled',  icon: 'Ban' },
}

const ALLOWED_TRANSITIONS: Record<string, string[]> = {
  STAFFED:             ['NO_GO', 'SUBMITTED_TO_CLIENT', 'CANCELLED'],
  SUBMITTED_TO_CLIENT: ['WON', 'LOST', 'CANCELLED'],
}

const canUpdateStatus = computed(() => {
  const role = authService.state.user?.role
  return role === 'admin' || role === 'commercial'
})

const availableTransitions = computed(() => {
  if (!mission.value) return []
  return ALLOWED_TRANSITIONS[mission.value.status] || []
})

const showStatusDropdown = ref(false)
const showHistoryModal = ref(false)
const statusHistory = ref<any[]>([])
const updatingStatus = ref(false)
const statusReason = ref('')
const selectedNewStatus = ref('')
const showReasonModal = ref(false)

const statusConfig = computed(() => {
  if (!mission.value?.status) return STATUS_CONFIG['STAFFED']
  return STATUS_CONFIG[mission.value.status] || STATUS_CONFIG['STAFFED']
})

const openReasonModal = (newStatus: string) => {
  selectedNewStatus.value = newStatus
  statusReason.value = ''
  showStatusDropdown.value = false
  showReasonModal.value = true
}

const confirmStatusUpdate = async () => {
  if (!mission.value || !selectedNewStatus.value) return
  updatingStatus.value = true
  try {
    await axios.patch(`/api/missions/missions/${mission.value.id}/status`, {
      status: selectedNewStatus.value,
      reason: statusReason.value || null,
    })
    await fetchMission()
  } catch (err: any) {
    alert('Erreur lors du changement de statut : ' + (err.response?.data?.detail || err.message))
  } finally {
    updatingStatus.value = false
    showReasonModal.value = false
  }
}

const openHistory = async () => {
  if (!mission.value) return
  try {
    const res = await axios.get(`/api/missions/missions/${mission.value.id}/status/history`)
    statusHistory.value = res.data
    showHistoryModal.value = true
  } catch (err) {
    alert('Impossible de charger l\'historique.')
  }
}

const statusText = computed(() => {
  if (pollCounter.value < 2) return "Ingestion documentaire (OCR/Parsing)..."
  if (pollCounter.value < 5) return "Extraction sémantique Gemini..."
  if (pollCounter.value < 8) return "Vérification des disponibilités (CV/Planning)..."
  return "Calcul des propositions de Staffing..."
})

</script>

<template>
  <div class="mission-detail-page">
    <div class="back-nav" @click="router.push('/missions')">
      <ChevronLeft size="20" /> Retour aux missions
    </div>

    <!-- Mode Création -->
    <div v-if="isNew && !mission" class="creation-mode">
      <div class="page-header">
        <Briefcase class="title-icon" size="28" />
        <div>
          <h1>Analyser une Fiche Mission</h1>
          <p>Chargez un appel d'offres (Google Doc, PDF, Word) ou collez le texte libre.</p>
        </div>
      </div>

      <div class="form-card">
        <div class="form-group">
          <label>Titre de la mission *</label>
          <input type="text" v-model="draftTitle" placeholder="Ex: Réfère Tech - Projet Cloud Native" />
        </div>
        
        <div class="source-grid">
          <div class="form-group source-item">
            <label>1. Fichier PDF / Word</label>
            <input type="file" @change="handleFileUpload" accept=".pdf,.doc,.docx" class="file-input" />
          </div>
          
          <div class="form-group source-item">
            <label>2. Ou Lien Google Docs / Web</label>
            <input type="url" v-model="draftUrl" placeholder="https://docs.google.com/document/d/..." />
          </div>
        </div>

        <div class="form-group">
          <label>3. Ou Texte libre / Compléments</label>
          <textarea v-model="draftDescription" rows="5" placeholder="Copiez-collez le texte ou ajoutez des instructions spécifiques..."></textarea>
        </div>
        
        <div class="form-actions">
          <button @click="analyzeMission" :disabled="!draftTitle || loading" class="submit-btn" :class="{ 'loading': loading }">
            <template v-if="!loading">Lancer l'IA Staffing <ArrowRight size="18" /></template>
            <template v-else><Loader2 class="spin" size="18" /> {{ statusText }}</template>
          </button>
        </div>
      </div>
    </div>

    <!-- Mode Détail (Existant ou Analysé) -->
    <div v-else-if="mission" class="detail-mode">
      <!-- Consultant Profile Highlight -->
      <ConsultantProfile
        v-if="selectedUserId"
        :userId="selectedUserId"
        @close="selectedUserId = null"
      />

      <!-- ── Status Bar ── -->
      <div class="status-bar">
        <span class="status-badge" :class="statusConfig.cssClass" aria-label="Statut de la mission">
          <component :is="statusConfig.cssClass === 'status-analysis' ? Loader2 : CheckCircle2" size="14" class="status-icon" :class="{ spin: statusConfig.cssClass === 'status-analysis' }" />
          {{ statusConfig.label }}
        </span>

        <div class="status-actions">
          <!-- Audit history -->
          <button class="btn-history" @click="openHistory" aria-label="Historique des statuts">
            <History size="15" /> Historique
          </button>

          <!-- Status dropdown (commercial / admin only) -->
          <div v-if="canUpdateStatus && availableTransitions.length > 0" class="status-dropdown-wrapper">
            <button
              class="btn-status-change"
              @click="showStatusDropdown = !showStatusDropdown"
              :disabled="updatingStatus"
              aria-label="Modifier le statut"
            >
              <span v-if="!updatingStatus">Changer le statut <ChevronDown size="14" /></span>
              <span v-else><Loader2 class="spin" size="14" /> En cours...</span>
            </button>
            <div v-if="showStatusDropdown" class="status-menu">
              <button
                v-for="target in availableTransitions"
                :key="target"
                class="status-menu-item"
                :class="STATUS_CONFIG[target]?.cssClass"
                @click="openReasonModal(target)"
              >
                {{ STATUS_CONFIG[target]?.label || target }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Reason Modal ── -->
      <div v-if="showReasonModal" class="modal-overlay" @click.self="showReasonModal = false">
        <div class="modal-card" role="dialog" aria-modal="true" aria-label="Motif du changement de statut">
          <h3>Confirmer le changement de statut</h3>
          <p>Nouveau statut : <strong class="status-badge" :class="STATUS_CONFIG[selectedNewStatus]?.cssClass">{{ STATUS_CONFIG[selectedNewStatus]?.label }}</strong></p>
          <label for="status-reason">Motif (recommandé pour l'audit)</label>
          <textarea id="status-reason" v-model="statusReason" rows="3" placeholder="Ex: Client hors budgets, compétences non couvertes..."></textarea>
          <div class="modal-actions">
            <button class="btn-cancel" @click="showReasonModal = false">Annuler</button>
            <button class="btn-confirm" @click="confirmStatusUpdate" :disabled="updatingStatus">
              <Loader2 v-if="updatingStatus" class="spin" size="14" /> Confirmer
            </button>
          </div>
        </div>
      </div>

      <!-- ── History Modal ── -->
      <div v-if="showHistoryModal" class="modal-overlay" @click.self="showHistoryModal = false">
        <div class="modal-card modal-wide" role="dialog" aria-modal="true" aria-label="Historique des statuts">
          <div class="modal-header">
            <h3><History size="18" /> Historique des statuts</h3>
            <button class="btn-close" @click="showHistoryModal = false" aria-label="Fermer">✕</button>
          </div>
          <div class="history-list">
            <div v-if="statusHistory.length === 0" class="empty-history">Aucun historique disponible.</div>
            <div v-for="entry in statusHistory" :key="entry.id" class="history-entry">
              <div class="history-timeline">
                <div class="history-dot"
                  :class="STATUS_CONFIG[entry.new_status]?.cssClass || 'status-draft'"
                ></div>
                <div class="history-line" v-if="entry !== statusHistory[statusHistory.length - 1]"></div>
              </div>
              <div class="history-content">
                <div class="history-transition">
                  <span v-if="entry.old_status" class="status-badge sm" :class="STATUS_CONFIG[entry.old_status]?.cssClass">{{ STATUS_CONFIG[entry.old_status]?.label || entry.old_status }}</span>
                  <span v-if="entry.old_status"> → </span>
                  <span class="status-badge sm" :class="STATUS_CONFIG[entry.new_status]?.cssClass">{{ STATUS_CONFIG[entry.new_status]?.label || entry.new_status }}</span>
                </div>
                <div class="history-meta">
                  <span>Par <strong>{{ entry.changed_by }}</strong></span>
                  <span>{{ new Date(entry.changed_at).toLocaleString('fr-FR') }}</span>
                </div>
                <div v-if="entry.reason" class="history-reason">{{ entry.reason }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="grid-layout">
        <!-- Colonne Gauche: Détails -->
        <div class="left-col">
          <div class="card mission-context">
            <div class="card-header">
              <h2>{{ mission.title }}</h2>
            </div>
            <div class="card-body">
              <div class="desc-box">
                <p>{{ mission.description }}</p>
              </div>
              
              <div class="section-title">
                <CheckCircle2 size="18" class="text-green" /> Compétences requises (Extract IA)
              </div>
              <div class="skills">
                <span v-for="skill in mission.extracted_competencies" :key="skill" class="skill-tag">
                  {{ skill }}
                </span>
              </div>
            </div>
          </div>
          
          <div class="card prefiltered-cvs" v-if="mission.prefiltered_candidates" style="margin-top: 2rem;">
            <div class="card-header highlight" style="background: rgba(16, 185, 129, 0.05);">
              <h3><Target size="20" /> CV Analysés (Pré-filtre RAG)</h3>
              <div style="display: flex; gap: 8px;">
                <span v-if="mission.fallback_full_scan" class="badge" style="background: #f59e0b;" title="Aucun CV n'est lié à ces compétences dans le graphe, la recherche RAG a fallback sur toute la BDD.">
                  <AlertTriangle size="12" style="display:inline; margin-bottom:-2px;" /> Full Scan (Fallback)
                </span>
                <span class="badge" style="background: #10b981;">Vector Search</span>
              </div>
            </div>
            <div class="card-body">
              <p style="font-size: 0.9rem; color: #666; margin-bottom: 1rem;">
                Candidats correspondants aux critères avant arbitrage final par l'IA de Staffing.
              </p>
              
              <div v-if="mission.prefiltered_candidates.length === 0" class="empty-state" style="padding: 1.5rem; text-align: center; color: #666; background: #fffbeb; border-radius: 8px; border: 1px dashed #f59e0b;">
                <AlertTriangle size="28" style="color: #f59e0b; margin-bottom: 0.5rem;" />
                <p style="font-weight: 500;">Aucun candidat correspondant trouvé.</p>
                <p style="font-size: 0.85rem; margin-top: 0.25rem;">Même après un Full Scan, la base de connaissance ne contient aucun profil pertinent.</p>
              </div>

              <div v-else class="team-list">
                <div 
                  v-for="cand in mission.prefiltered_candidates" 
                  :key="cand.user_id" 
                  class="team-member prefiltered-item clickable"
                  @click="selectedUserId = cand.user_id"
                >
                  <div class="member-header" style="margin-bottom: 0;">
                    <div class="member-identity">
                      <div class="avatar" style="width: 32px; height: 32px;"><UserIcon size="14" /></div>
                      <div>
                        <h4 style="font-size: 0.95rem;">{{ cand.full_name || 'Consultant Anonyme' }}</h4>
                        <span style="font-size: 0.75rem; color: #10b981; font-weight: 600;">Score: {{ (cand.similarity_score * 100).toFixed(1) }}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Colonne Droite: Équipe -->
        <div class="right-col">
          <div class="card team-proposal">
            <div class="card-header highlight">
              <h3><Users size="20" /> Équipe Proposée</h3>
              <div style="display: flex; gap: 12px; align-items: center;">
                 <button @click="reanalyzeMission" :disabled="pollingTask" class="reanalyze-btn">
                    <template v-if="!pollingTask">Relancer l'IA</template>
                    <template v-else><Loader2 class="spin" size="14" style="margin: 0; color: inherit;" /> En cours...</template>
                 </button>
                 <span class="badge">Staffing IA</span>
              </div>
            </div>
            <div class="card-body">
              <div v-if="(mission.proposed_team || []).filter((m: any) => m.user_id !== 0).length === 0" class="empty-state" style="padding: 2rem; text-align: center; color: #666;">
                <AlertTriangle size="32" style="color: #f59e0b; margin-bottom: 1rem;" />
                <p>Aucun consultant qualifié n'a pu être proposé pour cette mission.</p>
                <div v-if="mission.proposed_team && mission.proposed_team.length > 0 && mission.proposed_team[0].justification" style="margin-top: 1rem; padding: 1rem; background: #fff; border-left: 3px solid #f59e0b; border-radius: 6px; text-align: left; font-size: 0.9rem;">
                  <strong>Justification IA :</strong><br />
                  {{ mission.proposed_team[0].justification }}
                </div>
              </div>
              <div v-else class="team-list">
                <div 
                  v-for="member in mission.proposed_team.filter((m: any) => m.user_id !== 0)" 
                  :key="member.user_id" 
                  class="team-member clickable"
                  @click="selectedUserId = member.user_id"
                >
                  <div class="member-header">
                    <div class="member-identity">
                      <div class="avatar"><UserIcon size="18" /></div>
                      <div>
                        <h4>{{ member.full_name || 'Consultant' }}</h4>
                        <span class="role-badge" :class="getRoleColor(member.role)">{{ member.role }}</span>
                      </div>
                    </div>
                    <div class="estimate">
                      <Clock size="14" /> {{ member.estimated_days }} j
                    </div>
                  </div>
                  <p class="justification">{{ member.justification }}</p>
                  
                  <div class="availability-warning" v-if="Math.random() > 0.8"> <!-- Simulation, le backend fournit mais ce n'est pas persisté dans le model schema. On peut omettre -->
                     <AlertTriangle size="14" /> Indisponibilités détectées à proximité.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="loading && !isNew" class="loading-state">
      <Loader2 class="spin" size="32" />
      <p>Chargement de la mission...</p>
    </div>
  </div>
</template>

<style scoped>
.mission-detail-page {
  animation: fadeIn 0.4s ease;
  max-width: 1200px;
  margin: 0 auto;
}

.back-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-weight: 500;
  cursor: pointer;
  margin-bottom: 1.5rem;
  transition: color 0.2s;
  width: fit-content;
}
.back-nav:hover {
  color: var(--zenika-red);
}

.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2rem;
}
.title-icon {
  color: var(--zenika-red);
  background: rgba(227, 25, 55, 0.1);
  padding: 8px;
  border-radius: 12px;
  width: 48px;
  height: 48px;
}
h1 { font-size: 1.8rem; font-weight: 800; color: #1a1a1a; margin-bottom: 4px; }

.form-card {
  background: white;
  padding: 2rem;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}
.form-group {
  margin-bottom: 1.5rem;
}
.form-group label {
  display: block;
  font-weight: 600;
  margin-bottom: 8px;
  color: #333;
}
.form-group input, .form-group textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-family: inherit;
  font-size: 1rem;
  transition: all 0.2s;
  background: #fcfcfc;
}
.form-group input:focus, .form-group textarea:focus {
  outline: none;
  border-color: var(--zenika-red);
  background: white;
  box-shadow: 0 0 0 4px rgba(227, 25, 55, 0.1);
}

.source-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 1rem;
}
@media (max-width: 768px) {
  .source-grid {
    grid-template-columns: 1fr;
  }
}
.source-item {
  background: #fdfdfd;
  padding: 1rem;
  border-radius: 8px;
  border: 1px dashed #cbd5e1;
  transition: border-color 0.2s;
}
.source-item:hover {
  border-color: var(--zenika-red);
}
.file-input {
  padding: 8px;
  background: white;
}

.submit-btn {
  display: flex;

  align-items: center;
  justify-content: center;
  gap: 10px;
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 14px 28px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.2s;
  width: 100%;
}
.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.submit-btn:not(:disabled):hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(227, 25, 55, 0.25);
}

/* Detail View */
.grid-layout {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 2rem;
}
@media (max-width: 900px) {
  .grid-layout { grid-template-columns: 1fr; }
}

.card {
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  overflow: hidden;
}
.card-header {
  padding: 1.5rem;
  border-bottom: 1px solid #f0f0f0;
}
.card-header h2 { font-size: 1.4rem; font-weight: 700; }
.card-header.highlight {
  background: var(--bg-gradient);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-header.highlight h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 1.2rem;
  color: var(--zenika-red);
}
.badge {
  background: var(--zenika-red);
  color: white;
  font-size: 0.75rem;
  padding: 4px 8px;
  border-radius: 20px;
  font-weight: 600;
}
.card-body {
  padding: 1.5rem;
}

.desc-box {
  background: #f8f9fa;
  padding: 1rem;
  border-radius: 8px;
  font-size: 0.95rem;
  color: #444;
  line-height: 1.6;
  white-space: pre-wrap;
  margin-bottom: 2rem;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 1rem;
  font-size: 1.1rem;
}
.text-green { color: #10b981; }

.skills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.skill-tag {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 500;
}

.team-list {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
.team-member {
  padding: 1rem;
  border: 1px solid #eee;
  border-radius: 12px;
  background: #fbfbfc;
  transition: all 0.2s;
}
.team-member.clickable {
  cursor: pointer;
}
.team-member.clickable:hover {
  transform: translateY(-2px);
  border-color: var(--zenika-red);
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  background: white;
}
.member-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}
.member-identity {
  display: flex;
  gap: 12px;
  align-items: center;
}
.avatar {
  background: #eee;
  width: 40px;
  height: 40px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
}
.member-identity h4 {
  font-size: 1.05rem;
  font-weight: 600;
  margin-bottom: 4px;
}

.role-badge {
  font-size: 0.75rem;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
}
.reanalyze-btn {
  background: white;
  color: var(--zenika-red);
  border: 1px solid var(--zenika-red);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}
.reanalyze-btn:hover:not(:disabled) {
  background: var(--zenika-red);
  color: white;
}
.reanalyze-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.role-dp { background: #fee2e2; color: #b91c1c; }
.role-lead { background: #e0e7ff; color: #4338ca; }
.role-dev { background: #dcfce3; color: #15803d; }

.estimate {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  color: #666;
}

.justification {
  font-size: 0.9rem;
  color: #555;
  background: white;
  padding: 10px;
  border-radius: 6px;
  border-left: 3px solid #ccc;
}

.loading-state {
  text-align: center;
  padding: 4rem;
}
.spin { animation: spin 1s linear infinite; color: var(--zenika-red); margin-bottom: 1rem; }
@keyframes spin { 100% { transform: rotate(360deg); } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

/* ─── Status Bar ─────────────────────────────────── */
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 1.5rem;
  padding: 12px 16px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.status-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ─── Status Badges ──────────────────────────────── */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.status-badge.sm {
  padding: 3px 8px;
  font-size: 0.72rem;
}
.status-icon { flex-shrink: 0; }

.status-draft      { background: #f1f5f9; color: #475569; }
.status-analysis   { background: #eff6ff; color: #2563eb; }
.status-staffed    { background: #f0fdf4; color: #16a34a; }
.status-nogo       { background: #fef2f2; color: #dc2626; }
.status-submitted  { background: #f5f3ff; color: #7c3aed; }
.status-won        { background: #ecfdf5; color: #059669; border: 1px solid #6ee7b7; }
.status-lost       { background: #fff7ed; color: #ea580c; }
.status-cancelled  { background: #f8fafc; color: #64748b; border: 1px dashed #cbd5e1; }

/* ─── Buttons ────────────────────────────────────── */
.btn-history {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  color: #64748b;
  border: 1px solid #e2e8f0;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-history:hover { background: #f8fafc; color: #334155; border-color: #94a3b8; }

.btn-status-change {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-status-change:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-status-change:not(:disabled):hover { background: #c41230; box-shadow: 0 4px 12px rgba(227,25,55,0.3); }

/* ─── Dropdown ───────────────────────────────────── */
.status-dropdown-wrapper { position: relative; }
.status-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
  overflow: hidden;
  z-index: 100;
  min-width: 180px;
  animation: fadeIn 0.15s ease;
}
.status-menu-item {
  display: flex;
  align-items: center;
  width: 100%;
  padding: 10px 16px;
  border: none;
  background: transparent;
  text-align: left;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  border-radius: 0;
  gap: 8px;
}
.status-menu-item:hover { background: #f8fafc; }

/* ─── Modals ─────────────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}
.modal-card {
  background: white;
  border-radius: 16px;
  padding: 2rem;
  width: 460px;
  max-width: 95vw;
  box-shadow: 0 24px 48px rgba(0,0,0,0.18);
}
.modal-card.modal-wide { width: 560px; }
.modal-card h3 {
  font-size: 1.15rem;
  font-weight: 700;
  margin: 0 0 1rem;
  color: #1a1a1a;
}
.modal-card p { color: #555; margin-bottom: 1rem; font-size: 0.95rem; }
.modal-card label { display: block; font-weight: 600; font-size: 0.85rem; color: #333; margin-bottom: 6px; }
.modal-card textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-family: inherit;
  font-size: 0.9rem;
  resize: vertical;
}
.modal-card textarea:focus { outline: none; border-color: var(--zenika-red); box-shadow: 0 0 0 3px rgba(227,25,55,0.1); }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 1.25rem; }
.btn-cancel  { background: #f1f5f9; color: #64748b; border: none; padding: 8px 18px; border-radius: 8px; font-weight: 600; cursor: pointer; }
.btn-cancel:hover { background: #e2e8f0; }
.btn-confirm { background: var(--zenika-red); color: white; border: none; padding: 8px 18px; border-radius: 8px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.btn-confirm:disabled { opacity: 0.5; }
.btn-confirm:not(:disabled):hover { background: #c41230; }

/* ─── History Modal ──────────────────────────────── */
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; }
.modal-header h3 { display: flex; align-items: center; gap: 8px; margin: 0; }
.btn-close { background: none; border: none; font-size: 1.1rem; cursor: pointer; color: #94a3b8; transition: color 0.2s; }
.btn-close:hover { color: #334155; }
.history-list { display: flex; flex-direction: column; gap: 0; max-height: 55vh; overflow-y: auto; }
.empty-history { padding: 2rem; text-align: center; color: #94a3b8; font-size: 0.9rem; }

.history-entry {
  display: flex;
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px solid #f1f5f9;
}
.history-entry:last-child { border-bottom: none; }
.history-timeline {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 16px;
  flex-shrink: 0;
}
.history-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  margin-top: 4px;
  flex-shrink: 0;
}
.history-dot.status-staffed    { background: #16a34a; }
.history-dot.status-nogo       { background: #dc2626; }
.history-dot.status-submitted  { background: #7c3aed; }
.history-dot.status-won        { background: #059669; }
.history-dot.status-lost       { background: #ea580c; }
.history-dot.status-cancelled  { background: #64748b; }
.history-dot.status-analysis   { background: #2563eb; }
.history-dot.status-draft      { background: #94a3b8; }
.history-line { flex: 1; width: 2px; background: #e2e8f0; margin-top: 4px; }

.history-content { flex: 1; }
.history-transition { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 4px; }
.history-meta { font-size: 0.75rem; color: #94a3b8; display: flex; gap: 12px; margin-bottom: 4px; }
.history-meta strong { color: #475569; }
.history-reason {
  font-size: 0.8rem;
  color: #64748b;
  background: #f8fafc;
  padding: 6px 10px;
  border-radius: 6px;
  border-left: 3px solid #e2e8f0;
  margin-top: 4px;
}
</style>

