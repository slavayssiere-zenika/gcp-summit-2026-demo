<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import PageHeader from '../components/ui/PageHeader.vue'
import {
  PlayCircle, StopCircle, RefreshCcw, CheckCircle2,
  AlertCircle, Loader2, Upload, Cpu, Layers, Database,
  Coins, Clock, FileText, ChevronDown, ChevronUp, BarChart3, Zap, Trash2
} from 'lucide-vue-next'

// ── Types ─────────────────────────────────────────────────────────────────────

interface BulkStatus {
  status: 'idle' | 'building' | 'uploading' | 'batch_running' | 'applying' | 'completed' | 'error'
  total_cvs?: number
  applying_current?: number
  error_count?: number
  skipped_count?: number
  batch_job_id?: string
  dest_uri?: string
  total_tokens_input?: number
  total_tokens_output?: number
  logs?: string[]
  errors?: string[]
  error?: string | null
  start_time?: string
  end_time?: string
  updated_at?: string
  completion_stats?: { total: number; completed: number; failed: number; percent: number }
  vertex_state?: string
}

// ── State ─────────────────────────────────────────────────────────────────────

const status = ref<BulkStatus>({ status: 'idle' })
const isLoading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')
const showLogs = ref(true)
const showErrors = ref(false)
const pollingInterval = ref<any>(null)
const confirmStart = ref(false)
const isScoringLoading = ref(false)
const bulkScoringMsg = ref('')
const bulkScoringCount = ref<number | null>(null)
const scoringStatus = ref<any>({ status: 'idle' })
const scoringPollingInterval = ref<any>(null)


// ── Computed ──────────────────────────────────────────────────────────────────

const isActive = computed(() =>
  ['building', 'uploading', 'batch_running', 'applying'].includes(status.value.status)
)

const phaseLabel = computed(() => {
  const map: Record<string, string> = {
    idle: 'En attente',
    building: '🔨 Construction JSONL…',
    uploading: '☁️ Upload vers GCS…',
    batch_running: '⚡ Job Vertex AI Batch en cours…',
    applying: '🔄 Application des résultats…',
    completed: '✅ Terminé',
    error: '❌ Erreur',
  }
  return map[status.value.status] || status.value.status
})

const applyProgress = computed(() => {
  if (status.value.status === 'batch_running') {
    const cs = status.value.completion_stats
    if (cs) return cs.percent
    return null
  }
  if (status.value.status === 'applying') {
    const total = status.value.total_cvs || 1
    const done = status.value.applying_current || 0
    return Math.round((done / total) * 100)
  }
  if (status.value.status === 'completed') return 100
  return null
})

const elapsedTime = computed(() => {
  if (!status.value.start_time) return null
  const start = new Date(status.value.start_time).getTime()
  const end = status.value.end_time ? new Date(status.value.end_time).getTime() : Date.now()
  const diff = Math.floor((end - start) / 1000)
  const m = Math.floor(diff / 60)
  const s = diff % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
})

const elapsedSeconds = computed(() => {
  if (!status.value.start_time) return 0
  const start = new Date(status.value.start_time).getTime()
  const end = status.value.end_time ? new Date(status.value.end_time).getTime() : Date.now()
  return Math.max(1, Math.floor((end - start) / 1000))
})

// Pour le DÉBIT : on utilise apply_start_time (début de la phase APPLY)
// et non start_time (début du pipeline entier qui inclut le Vertex AI Batch Job).
// Cela évite un taux biaisé de type "0.2 CVs/min" pendant 2h de batch.
const applyElapsedSeconds = computed(() => {
  const applyStart = status.value.apply_start_time || status.value.start_time
  if (!applyStart) return 0
  const start = new Date(applyStart).getTime()
  const end = status.value.end_time ? new Date(status.value.end_time).getTime() : Date.now()
  return Math.max(1, Math.floor((end - start) / 1000))
})

const throughputCvPerMin = computed(() => {
  const done = status.value.applying_current || 0
  if (!done || !status.value.apply_start_time) return null
  const rate = (done / applyElapsedSeconds.value) * 60
  return rate.toFixed(1)
})

const estimatedRemainingMin = computed(() => {
  const done = status.value.applying_current || 0
  const total = status.value.total_cvs || 0
  if (!done || !throughputCvPerMin.value || done >= total) return null
  const remaining = (total - done) / parseFloat(throughputCvPerMin.value)
  return remaining < 1 ? '<1 min' : `~${Math.ceil(remaining)} min`
})

const totalTokens = computed(() =>
  (status.value.total_tokens_input || 0) + (status.value.total_tokens_output || 0)
)

const estimatedCostEur = computed(() => {
  const input = (status.value.total_tokens_input || 0) / 1_000_000 * 0.075
  const output = (status.value.total_tokens_output || 0) / 1_000_000 * 0.30
  return (input + output).toFixed(4)
})

// ── Actions ───────────────────────────────────────────────────────────────────

const fetchStatus = async () => {
  try {
    const res = await axios.get('/api/cv/bulk-reanalyse/status')
    status.value = res.data
  } catch (e: any) {
    console.error('Status fetch error', e)
  }
}

const startPipeline = async () => {
  if (!confirmStart.value) {
    errorMsg.value = 'Veuillez cocher la case de confirmation avant de démarrer.'
    return
  }
  isLoading.value = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    const res = await axios.post('/api/cv/bulk-reanalyse/start')
    successMsg.value = res.data.message || 'Pipeline démarré.'
    confirmStart.value = false
    await fetchStatus()
    startPolling()
  } catch (e: any) {
    const detail = e.response?.data?.detail || e.message
    errorMsg.value = `Erreur démarrage : ${detail}`
  } finally {
    isLoading.value = false
  }
}

const cancelPipeline = async () => {
  if (!confirm('Êtes-vous sûr de vouloir annuler la ré-analyse en cours ?')) return
  isLoading.value = true
  errorMsg.value = ''
  try {
    const res = await axios.post('/api/cv/bulk-reanalyse/cancel')
    successMsg.value = res.data.message || 'Pipeline annulé.'
    stopPolling()
    await fetchStatus()
  } catch (e: any) {
    errorMsg.value = `Erreur annulation : ${e.response?.data?.detail || e.message}`
  } finally {
    isLoading.value = false
  }
}

const resetPipeline = async () => {
  isLoading.value = true
  errorMsg.value = ''
  try {
    await axios.post('/api/cv/bulk-reanalyse/reset')
    successMsg.value = 'État réinitialisé — vous pouvez relancer le pipeline.'
    await fetchStatus()
  } catch (e: any) {
    errorMsg.value = `Erreur réinitialisation : ${e.response?.data?.detail || e.message}`
  } finally {
    isLoading.value = false
  }
}

const retryApply = async () => {
  isLoading.value = true
  errorMsg.value = ''
  try {
    const res = await axios.post('/api/cv/bulk-reanalyse/retry-apply')
    successMsg.value = res.data.message || 'Retry apply démarré.'
    await fetchStatus()
    startPolling()
  } catch (e: any) {
    errorMsg.value = `Erreur retry apply : ${e.response?.data?.detail || e.message}`
  } finally {
    isLoading.value = false
  }
}

const triggerBulkScoring = async (force = false) => {
  isScoringLoading.value = true
  bulkScoringMsg.value = ''
  bulkScoringCount.value = null
  try {
    const res = await axios.post('/api/competencies/evaluations/bulk-scoring-all', null, {
      params: { force, semaphore_limit: 2 }
    })
    bulkScoringCount.value = res.data.triggered
    bulkScoringMsg.value = res.data.message
    fetchScoringStatus()
  } catch (e: any) {
    bulkScoringMsg.value = `Erreur : ${e.response?.data?.detail || e.message}`
  } finally {
    isScoringLoading.value = false
  }
}

const cancelBulkScoring = async () => {
  if (!confirm("Voulez-vous annuler le scoring en cours ?")) return
  try {
    await axios.post('/api/competencies/bulk-scoring-all/cancel')
    await fetchScoringStatus()
  } catch (e) {
    console.error("Cancel failed", e)
  }
}

const fetchScoringStatus = async () => {
  try {
    const res = await axios.get('/api/competencies/bulk-scoring-all/status')
    scoringStatus.value = res.data
    if (scoringStatus.value.status === 'running') {
      startScoringPolling()
    } else {
      stopScoringPolling()
    }
  } catch (e) {
    console.error('Fetch scoring status failed', e)
    stopScoringPolling()
  }
}



// ── Polling ───────────────────────────────────────────────────────────────────

const startPolling = () => {
  if (pollingInterval.value) return
  pollingInterval.value = setInterval(async () => {
    await fetchStatus()
    if (!isActive.value) stopPolling()
  }, 5000)
}

const stopPolling = () => {
  if (pollingInterval.value) {
    clearInterval(pollingInterval.value)
    pollingInterval.value = null
  }
}

const startScoringPolling = () => {
  if (scoringPollingInterval.value) return
  scoringPollingInterval.value = setInterval(async () => {
    await fetchScoringStatus()
  }, 2000)
}

const stopScoringPolling = () => {
  if (scoringPollingInterval.value) {
    clearInterval(scoringPollingInterval.value)
    scoringPollingInterval.value = null
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  await fetchStatus()
  if (isActive.value) startPolling()
  
  await fetchScoringStatus()
})

onUnmounted(() => stopPolling())

// ── Utils ─────────────────────────────────────────────────────────────────────

const formatN = (n?: number) => (n ?? 0).toLocaleString('fr-FR')
const lastLog = computed(() => {
  const logs = status.value.logs || []
  return logs.length > 0 ? logs[logs.length - 1].replace(/^\[.*?\]\s*/, '') : '—'
})
</script>

<template>
  <div class="bulk-import-view">
    <PageHeader
      title="Ré-analyse Globale des CVs"
      subtitle="Pipeline Vertex AI Batch — Option B (Intégrité Totale)"
    />

    <!-- Alertes ── -->
    <div v-if="errorMsg" class="alert alert-error">
      <AlertCircle :size="18" /> {{ errorMsg }}
    </div>
    <div v-if="successMsg" class="alert alert-success">
      <CheckCircle2 :size="18" /> {{ successMsg }}
    </div>

    <!-- Phase indicator ── -->
    <div class="phase-pipeline">
      <div
        v-for="(phase, i) in ['building', 'uploading', 'batch_running', 'applying', 'completed']"
        :key="phase"
        class="phase-step"
        :class="{
          active: status.status === phase,
          done: ['building','uploading','batch_running','applying','completed'].indexOf(status.status) > i,
          error: status.status === 'error'
        }"
      >
        <div class="phase-dot">
          <CheckCircle2 v-if="['building','uploading','batch_running','applying','completed'].indexOf(status.status) > i" :size="16" />
          <Loader2 v-else-if="status.status === phase" :size="16" class="spin" />
          <span v-else class="dot-num">{{ i + 1 }}</span>
        </div>
        <span class="phase-label">{{ ['Build', 'Upload', 'Vertex Batch', 'Apply', 'Terminé'][i] }}</span>
        <div v-if="i < 4" class="phase-connector" :class="{ done: ['building','uploading','batch_running','applying','completed'].indexOf(status.status) > i }" />
      </div>
    </div>

    <!-- Status Card ── -->
    <div class="status-card" :class="status.status">
      <div class="status-header">
        <span class="status-badge">{{ phaseLabel }}</span>
        <span v-if="elapsedTime" class="status-elapsed"><Clock :size="14" /> {{ elapsedTime }}</span>
      </div>

      <!-- Progress Bar ── -->
      <div v-if="applyProgress !== null" class="progress-wrap">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: applyProgress + '%' }" />
        </div>
        <span class="progress-pct">{{ applyProgress }}%</span>
      </div>

      <!-- Vertex completion_stats ── -->
      <div v-if="status.completion_stats" class="vertex-stats">
        <div class="stat-item">
          <Cpu :size="14" /> Vertex : {{ formatN(status.completion_stats.completed) }} / {{ formatN(status.completion_stats.total) }} CVs
        </div>
        <div class="stat-item error-stat" v-if="status.completion_stats.failed > 0">
          <AlertCircle :size="14" /> {{ formatN(status.completion_stats.failed) }} échecs Vertex
        </div>
      </div>

      <!-- Apply stats ── -->
      <div v-if="status.status === 'applying' || status.status === 'completed'" class="apply-stats">
        <div class="stat-item"><Database :size="14" /> {{ formatN(status.applying_current) }} / {{ formatN(status.total_cvs) }} CVs appliqués</div>
        <div class="stat-item speed-stat" v-if="throughputCvPerMin && status.status === 'applying'">
          <Zap :size="14" /> {{ throughputCvPerMin }} CVs/min
          <span v-if="estimatedRemainingMin" class="remaining-label">({{ estimatedRemainingMin }})</span>
        </div>
        <div class="stat-item error-stat" v-if="(status.error_count || 0) > 0"><AlertCircle :size="14" /> {{ formatN(status.error_count) }} erreurs apply</div>
        <div class="stat-item" v-if="(status.skipped_count || 0) > 0"><FileText :size="14" /> {{ formatN(status.skipped_count) }} ignorés</div>
      </div>
      <!-- Post-apply banner : Bulk Scoring requis ── -->
      <div v-if="status.status === 'completed'" class="post-apply-banner">
        <Zap :size="16" />
        <span>Apply terminé. <strong>Lancez le Bulk Scoring</strong> pour calculer les scores IA des compétences.</span>
      </div>

      <!-- Last log ── -->
      <p v-if="lastLog !== '—'" class="last-log">{{ lastLog }}</p>

      <!-- Error detail ── -->
      <div v-if="status.status === 'error' && status.error" class="error-detail">
        <AlertCircle :size="14" />
        <span>{{ status.error }}</span>
      </div>

      <!-- Job ID ── -->
      <p v-if="status.batch_job_id" class="job-id">
        <Layers :size="12" />
        <span>{{ status.batch_job_id.split('/').pop() }}</span>
      </p>
    </div>

    <!-- FinOps Card ── -->
    <div v-if="totalTokens > 0" class="finops-card">
      <h3><Coins :size="16" /> FinOps — Consommation Tokens</h3>
      <div class="finops-grid">
        <div class="finops-item">
          <span class="finops-label">Tokens Input</span>
          <span class="finops-value">{{ formatN(status.total_tokens_input) }}</span>
        </div>
        <div class="finops-item">
          <span class="finops-label">Tokens Output</span>
          <span class="finops-value">{{ formatN(status.total_tokens_output) }}</span>
        </div>
        <div class="finops-item">
          <span class="finops-label">Total Tokens</span>
          <span class="finops-value">{{ formatN(totalTokens) }}</span>
        </div>
        <div class="finops-item highlight">
          <span class="finops-label">Coût estimé</span>
          <span class="finops-value">~{{ estimatedCostEur }} €</span>
        </div>
      </div>
    </div>

    <!-- Logs ── -->
    <div v-if="(status.logs || []).length > 0" class="logs-section">
      <div class="logs-header" @click="showLogs = !showLogs">
        <span><BarChart3 :size="15" /> Logs pipeline ({{ (status.logs || []).length }})</span>
        <ChevronDown v-if="!showLogs" :size="15" />
        <ChevronUp v-else :size="15" />
      </div>
      <div v-if="showLogs" class="logs-list">
        <p v-for="(log, i) in [...(status.logs || [])].reverse().slice(0, 60)" :key="i" class="log-line">{{ log }}</p>
      </div>
    </div>

    <!-- Errors ── -->
    <div v-if="(status.errors || []).length > 0" class="errors-section">
      <div class="logs-header error-header" @click="showErrors = !showErrors">
        <span><AlertCircle :size="15" /> Erreurs ({{ (status.errors || []).length }})</span>
        <ChevronDown v-if="!showErrors" :size="15" />
        <ChevronUp v-else :size="15" />
      </div>
      <div v-if="showErrors" class="logs-list">
        <p v-for="(err, i) in (status.errors || []).slice().reverse()" :key="i" class="log-line error-line">{{ err }}</p>
      </div>
    </div>

    <!-- Workflow Guidé ── -->
    <div class="workflow-steps">
      
      <!-- Étape 1 : Pipeline Vertex AI -->
      <div class="step-box" :class="{ 'step-current': !isActive && status.status !== 'completed', 'step-done': status.status === 'completed' }">
        <div class="step-header">
          <div class="step-num"><CheckCircle2 v-if="status.status === 'completed'" size="16" /><span v-else>1</span></div>
          <div class="step-title-wrap">
            <h3>Pipeline Vertex AI Batch</h3>
            <p class="step-desc">Extrait et formate les CV en masse. Purge les données existantes.</p>
          </div>
        </div>
        <div class="step-content">
          <!-- START ── -->
          <div v-if="!isActive && !['completed', 'error', 'cancelled'].includes(status.status)" class="start-block">
            <div class="confirm-check">
              <input id="confirm-check" type="checkbox" v-model="confirmStart" />
              <label for="confirm-check">
                Je confirme vouloir lancer la ré-analyse globale. Cette opération
                <strong>purge et régénère toutes les données</strong> (compétences,
                missions, scores) pour l'ensemble des consultants.
              </label>
            </div>
            <button
              class="btn btn-primary"
              :disabled="isLoading || !confirmStart"
              @click="startPipeline"
              aria-label="Démarrer la ré-analyse globale"
            >
              <Loader2 v-if="isLoading" :size="18" class="spin" />
              <PlayCircle v-else :size="18" />
              Démarrer le pipeline (Étape 1)
            </button>
          </div>

          <!-- CANCEL / REFRESH ── -->
          <div v-if="isActive" class="active-actions">
            <button class="btn btn-danger" @click="cancelPipeline" :disabled="isLoading" aria-label="Annuler le pipeline">
              <StopCircle :size="18" />
              Annuler l'exécution
            </button>
            <button class="btn btn-ghost" @click="fetchStatus" aria-label="Rafraîchir le statut">
              <RefreshCcw :size="18" />
              Rafraîchir
            </button>
          </div>
          
          <div v-if="status.status === 'completed'" class="step-success-msg">
            <CheckCircle2 size="16" /> Pipeline terminé avec succès. Passez à l'étape 2.
          </div>
        </div>
      </div>

      <!-- Bloc Résolution des erreurs -->
      <div v-if="['error', 'cancelled'].includes(status.status) || (status.status === 'completed' && (status.error_count || 0) > 0)" class="step-box step-warning">
        <div class="step-header">
          <div class="step-num bg-warning"><AlertCircle size="16" /></div>
          <div class="step-title-wrap">
            <h3 class="text-warning">Rattrapage & Résolution</h3>
            <p class="step-desc">Le pipeline a été interrompu ou des erreurs d'application sont survenues.</p>
          </div>
        </div>
        <div class="step-content">
          <div class="post-actions">
            <button
              v-if="status.status === 'cancelled' || status.status === 'error' || (status.status === 'completed' && (status.error_count || 0) > 0)"
              class="btn btn-warning"
              :disabled="isLoading"
              @click="retryApply"
              aria-label="Retry apply depuis GCS sans relancer Vertex"
            >
              <Loader2 v-if="isLoading" :size="18" class="spin" />
              <RefreshCcw v-else :size="18" />
              Re-tenter l'application (Depuis GCS)
              <span v-if="status.status === 'cancelled'" class="badge-gcs">Données Vertex préservées</span>
            </button>
            <button
              v-if="status.status === 'error' || status.status === 'cancelled'"
              class="btn btn-reset"
              :disabled="isLoading"
              @click="resetPipeline"
              aria-label="Vider l'état et Recommencer à zéro"
            >
              <Loader2 v-if="isLoading" :size="18" class="spin" />
              <Trash2 v-else :size="18" />
              Vider l'état et recommencer à zéro
            </button>
            <button class="btn btn-ghost" @click="fetchStatus" aria-label="Rafraîchir le statut">
              <RefreshCcw :size="18" />
              Rafraîchir
            </button>
          </div>
        </div>
      </div>

      <!-- Étape 2 : Scoring IA -->
      <div class="step-box" :class="{ 'step-current': status.status === 'completed', 'step-disabled': status.status !== 'completed' && !['error', 'cancelled'].includes(status.status) }">
        <div class="step-header">
          <div class="step-num">2</div>
          <div class="step-title-wrap">
            <h3>Scoring IA des Compétences</h3>
            <p class="step-desc">Calcule les scores IA pour tous les consultants. Indispensable après l'étape 1.</p>
          </div>
        </div>
        <div class="step-content">
          <div class="scoring-section" :class="{ 'scoring-cta': status.status === 'completed' }">
            <div class="scoring-actions">
              <button
                class="btn btn-scoring"
                :class="{ 'btn-primary-pulse': status.status === 'completed' && scoringStatus.status !== 'completed' && scoringStatus.status !== 'running' }"
                :disabled="isScoringLoading || (status.status !== 'completed' && !['error', 'cancelled'].includes(status.status))"
                @click="triggerBulkScoring(false)"
                aria-label="Calculer les scores manquants"
              >
                <Loader2 v-if="isScoringLoading" :size="16" class="spin" />
                <Zap v-else :size="16" />
                Lancer le Scoring (Étape 2)
              </button>
              <button
                class="btn btn-scoring-force"
                :disabled="isScoringLoading || (status.status !== 'completed' && !['error', 'cancelled'].includes(status.status))"
                @click="triggerBulkScoring(true)"
                aria-label="Re-scorer absolument tous les consultants"
              >
                <Loader2 v-if="isScoringLoading" :size="16" class="spin" />
                <RefreshCcw v-else :size="16" />
                Forcer un recalcul total
              </button>
            </div>
            
            <!-- Progression du Scoring IA -->
            <div v-if="scoringStatus.status === 'running'" class="scoring-progress-box">
              <div class="progress-header">
                <span class="progress-title">Scoring en cours...</span>
                <span class="progress-stats">
                  {{ scoringStatus.processed }} / {{ scoringStatus.total_users }} consultants
                </span>
              </div>
              <div class="progress-bar-bg">
                <div 
                  class="progress-bar-fill bg-blue"
                  :style="{ width: `${(scoringStatus.processed / (scoringStatus.total_users || 1)) * 100}%` }"
                ></div>
              </div>
              <div class="progress-details">
                <span class="text-success">✅ {{ scoringStatus.success }} succès</span>
                <span v-if="scoringStatus.error_count > 0" class="text-danger">❌ {{ scoringStatus.error_count }} erreurs</span>
                <button class="btn btn-ghost btn-cancel-sm" @click="cancelBulkScoring">Annuler</button>
              </div>
            </div>
            <div v-else-if="scoringStatus.status === 'completed'" class="scoring-feedback scoring-ok">
              <span class="scoring-count">✅ Scoring Terminé</span>
              {{ scoringStatus.success }} succès, {{ scoringStatus.error_count }} erreurs.
            </div>
            <div v-else-if="scoringStatus.status === 'error'" class="scoring-feedback bg-danger">
              <span class="scoring-count">❌ Erreur Scoring</span>
              {{ scoringStatus.errors?.[0] }}
            </div>
            <div v-else-if="bulkScoringMsg" class="scoring-feedback" :class="{ 'scoring-ok': bulkScoringCount !== null && bulkScoringCount > 0 }">
              <span v-if="bulkScoringCount !== null" class="scoring-count">{{ bulkScoringCount }} consultant(s)</span>
              {{ bulkScoringMsg }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bulk-import-view {
  max-width: 900px;
  margin: 0 auto;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  color: var(--color-text-primary, #e2e8f0);
}

/* Alerts */
.alert {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
}
.alert-error { background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: #fca5a5; }
.alert-success { background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.3); color: #86efac; }

/* Phase pipeline */
.phase-pipeline {
  display: flex;
  align-items: center;
  gap: 0;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 1rem 1.5rem;
  overflow-x: auto;
}
.phase-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
  position: relative;
  flex: 1;
  min-width: 70px;
}
.phase-dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.04);
  font-size: 0.75rem;
  color: #94a3b8;
  transition: all 0.3s;
  z-index: 1;
}
.phase-step.active .phase-dot { border-color: #6366f1; background: rgba(99,102,241,0.2); color: #818cf8; }
.phase-step.done .phase-dot { border-color: #22c55e; background: rgba(34,197,94,0.2); color: #86efac; }
.phase-step.error .phase-dot { border-color: #ef4444; background: rgba(239,68,68,0.2); color: #fca5a5; }
.phase-label { font-size: 0.7rem; color: #94a3b8; text-align: center; white-space: nowrap; }
.phase-step.active .phase-label { color: #818cf8; font-weight: 600; }
.phase-step.done .phase-label { color: #86efac; }
.phase-connector {
  position: absolute;
  top: 16px;
  right: -50%;
  width: 100%;
  height: 2px;
  background: rgba(255,255,255,0.1);
}
.phase-connector.done { background: #22c55e; }
.dot-num { font-size: 0.75rem; color: #64748b; }

/* Status card */
.status-card {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.status-card.error { border-color: rgba(239,68,68,0.3); background: rgba(239,68,68,0.05); }
.status-card.completed { border-color: rgba(34,197,94,0.3); background: rgba(34,197,94,0.05); }
.status-card.batch_running { border-color: rgba(99,102,241,0.3); }
.status-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.status-badge {
  font-size: 0.95rem;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.status-elapsed { display: flex; align-items: center; gap: 0.3rem; font-size: 0.8rem; color: #94a3b8; }

/* Progress bar */
.progress-wrap { display: flex; align-items: center; gap: 0.75rem; }
.progress-bar {
  flex: 1;
  height: 8px;
  background: rgba(255,255,255,0.08);
  border-radius: 999px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #818cf8);
  border-radius: 999px;
  transition: width 0.6s ease;
}
.status-card.completed .progress-fill { background: linear-gradient(90deg, #22c55e, #86efac); }
.progress-pct { font-size: 0.85rem; color: #94a3b8; min-width: 36px; text-align: right; }

/* Stats */
.vertex-stats, .apply-stats { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.stat-item { display: flex; align-items: center; gap: 0.35rem; font-size: 0.82rem; color: #94a3b8; }
.error-stat { color: #fca5a5; }

.last-log { font-size: 0.8rem; color: #64748b; font-style: italic; margin: 0; }
.job-id { display: flex; align-items: center; gap: 0.4rem; font-size: 0.72rem; color: #475569; font-family: monospace; margin: 0; }
.error-detail {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  background: rgba(239,68,68,0.1);
  border: 1px solid rgba(239,68,68,0.25);
  border-radius: 8px;
  font-size: 0.82rem;
  color: #fca5a5;
  font-family: monospace;
  word-break: break-all;
}

/* FinOps */
.finops-card {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(99,102,241,0.2);
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
}
.finops-card h3 { display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; font-weight: 600; color: #818cf8; margin: 0 0 1rem; }
.finops-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; }
@media (min-width: 600px) { .finops-grid { grid-template-columns: repeat(4, 1fr); } }
.finops-item { background: rgba(255,255,255,0.03); border-radius: 8px; padding: 0.75rem; }
.finops-item.highlight { background: rgba(99,102,241,0.1); border: 1px solid rgba(99,102,241,0.2); }
.finops-label { display: block; font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.25rem; }
.finops-value { font-size: 1rem; font-weight: 700; color: #e2e8f0; }
.finops-item.highlight .finops-value { color: #a5b4fc; }

/* Logs */
.logs-section, .errors-section {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 12px;
  overflow: hidden;
}
.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1.25rem;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
  color: #94a3b8;
  transition: background 0.2s;
}
.logs-header:hover { background: rgba(255,255,255,0.04); }
.error-header { color: #fca5a5; }
.logs-header span { display: flex; align-items: center; gap: 0.4rem; }
.logs-list {
  max-height: 320px;
  overflow-y: auto;
  padding: 0.75rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.log-line {
  font-size: 0.78rem;
  color: #64748b;
  font-family: monospace;
  margin: 0;
  line-height: 1.6;
}
.error-line { color: #fca5a5; }

/* Actions */
.workflow-steps {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin-top: 1rem;
}
.step-box {
  background: var(--surface-light);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}
.step-box.step-current {
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
}
.step-box.step-done {
  border-color: rgba(16, 185, 129, 0.3);
}
.step-box.step-warning {
  border-color: rgba(245, 158, 11, 0.4);
  background: rgba(245, 158, 11, 0.02);
}
.step-box.step-disabled {
  opacity: 0.6;
  filter: grayscale(0.5);
}
.step-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1.25rem 1.5rem;
  background: rgba(0, 0, 0, 0.02);
  border-bottom: 1px solid var(--border-color);
}
.step-num {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary, #3b82f6);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1rem;
  flex-shrink: 0;
}
.step-num.bg-warning {
  background: #f59e0b;
}
.step-title-wrap h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text-primary, #1e293b);
}
.step-title-wrap h3.text-warning {
  color: #d97706;
}
.step-desc {
  margin: 0.25rem 0 0;
  font-size: 0.85rem;
  color: var(--text-light, #64748b);
}
.step-content {
  padding: 1.5rem;
}
.step-success-msg {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #10b981;
  font-weight: 600;
  background: rgba(16, 185, 129, 0.1);
  padding: 1rem;
  border-radius: 8px;
}
.btn-primary-pulse {
  animation: pulsePrimary 2s infinite;
}
@keyframes pulsePrimary {
  0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(59, 130, 246, 0); }
  100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0); }
}
.confirm-check {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: rgba(239,68,68,0.07);
  border: 1px solid rgba(239,68,68,0.2);
  border-radius: 10px;
  font-size: 0.85rem;
  line-height: 1.5;
  color: #fca5a5;
}
.confirm-check input { margin-top: 0.15rem; accent-color: #ef4444; flex-shrink: 0; cursor: pointer; }
.confirm-check label { cursor: pointer; }

.start-block, .active-actions, .post-actions { display: flex; flex-direction: column; gap: 0.75rem; }

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.65rem 1.5rem;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 180px;
  width: fit-content;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: linear-gradient(135deg, #6366f1, #4f46e5); color: #fff; }
.btn-primary:hover:not(:disabled) { background: linear-gradient(135deg, #818cf8, #6366f1); transform: translateY(-1px); box-shadow: 0 4px 16px rgba(99,102,241,0.3); }
.btn-danger { background: rgba(239,68,68,0.15); color: #fca5a5; border: 1px solid rgba(239,68,68,0.3); }
.btn-danger:hover:not(:disabled) { background: rgba(239,68,68,0.25); }
.btn-ghost { background: rgba(255,255,255,0.06); color: #94a3b8; border: 1px solid rgba(255,255,255,0.1); }
.btn-ghost:hover:not(:disabled) { background: rgba(255,255,255,0.1); color: #cbd5e1; }
.btn-reset { background: rgba(245,158,11,0.12); color: #fbbf24; border: 1px solid rgba(245,158,11,0.25); }
.btn-reset:hover:not(:disabled) { background: rgba(245,158,11,0.22); }
.btn-warning { background: rgba(99,102,241,0.12); color: #a5b4fc; border: 1px solid rgba(99,102,241,0.25); }
.btn-warning:hover:not(:disabled) { background: rgba(99,102,241,0.22); }
.badge-gcs {
  display: inline-block; margin-left: 6px; padding: 1px 6px;
  background: rgba(16,185,129,0.15); color: #34d399;
  border: 1px solid rgba(16,185,129,0.3); border-radius: 4px;
  font-size: 10px; font-weight: 600; vertical-align: middle; text-transform: uppercase; letter-spacing: 0.05em;
}

.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* Speed stat */
.speed-stat { color: #34d399; font-weight: 600; }
.remaining-label { color: #64748b; font-weight: 400; margin-left: 0.25rem; }

/* Post-apply banner */
.post-apply-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding: 0.65rem 1rem;
  background: rgba(245,158,11,0.1);
  border: 1px solid rgba(245,158,11,0.3);
  border-radius: 8px;
  font-size: 0.85rem;
  color: #fcd34d;
}
.post-apply-banner strong { color: #fbbf24; }

/* Bulk Scoring Section */
.scoring-section {
  background: rgba(245, 158, 11, 0.06);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  transition: all 0.3s;
}
.scoring-section.scoring-cta {
  background: rgba(245, 158, 11, 0.14);
  border-color: rgba(245, 158, 11, 0.5);
  box-shadow: 0 0 20px rgba(245,158,11,0.15);
}
.scoring-cta-badge {
  margin-left: auto;
  padding: 2px 8px;
  background: rgba(245,158,11,0.2);
  border: 1px solid rgba(245,158,11,0.4);
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 700;
  color: #fcd34d;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  animation: pulse-badge 2s ease-in-out infinite;
}
@keyframes pulse-badge {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
.scoring-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1rem;
  font-weight: 700;
  color: #fbbf24;
}
.scoring-icon { color: #f59e0b; }
.scoring-desc {
  font-size: 0.85rem;
  color: #94a3b8;
  margin: 0;
  line-height: 1.5;
}
.scoring-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.btn-scoring {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.35);
}
.btn-scoring:hover:not(:disabled) {
  background: rgba(245, 158, 11, 0.28);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(245, 158, 11, 0.2);
}
.btn-scoring-force {
  background: rgba(239, 68, 68, 0.1);
  color: #fca5a5;
  border: 1px solid rgba(239, 68, 68, 0.25);
}
.btn-scoring-force:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
  transform: translateY(-1px);
}
.scoring-feedback {
  font-size: 0.85rem;
  color: #94a3b8;
  padding: 0.6rem 0.9rem;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.scoring-feedback.scoring-ok {
  background: rgba(34, 197, 94, 0.08);
  border-color: rgba(34, 197, 94, 0.2);
  color: #86efac;
}
.scoring-count {
  font-weight: 700;
  margin-right: 0.4rem;
  color: #fbbf24;
}

/* ── Scoring Progress Tracker ── */
.scoring-progress-box {
  background: rgba(15, 23, 42, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 1rem;
  margin-top: 1rem;
}
.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
}
.progress-title {
  font-weight: 600;
  color: #e2e8f0;
}
.progress-stats {
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}
.progress-bar-bg {
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 0.75rem;
}
.progress-bar-fill {
  height: 100%;
  transition: width 0.3s ease;
}
.bg-blue { background-color: #3b82f6; }
.progress-details {
  display: flex;
  align-items: center;
  gap: 1rem;
  font-size: 0.85rem;
}
.text-success { color: #10b981; }
.text-danger { color: #ef4444; }
.bg-danger { 
  background: rgba(239, 68, 68, 0.1) !important; 
  border-color: rgba(239, 68, 68, 0.2) !important;
  color: #fca5a5 !important;
}
.btn-cancel-sm {
  margin-left: auto;
  padding: 0.25rem 0.75rem;
  font-size: 0.8rem;
  border-color: rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}
.btn-cancel-sm:hover {
  background: rgba(239, 68, 68, 0.1);
}


</style>
