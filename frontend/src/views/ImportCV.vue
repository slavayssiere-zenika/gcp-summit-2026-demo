<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import { FileDown, RefreshCw, CheckCircle, AlertCircle, Lock, AlertTriangle, ChevronRight } from 'lucide-vue-next'
import { authService } from '../services/auth'

// ─── Types ────────────────────────────────────────────────────────────────────
interface CVImportStep {
  step: string
  label: string
  status: 'success' | 'warning' | 'error' | 'skipped' | 'pending' | 'running'
  duration_ms?: number
  detail?: string
}

interface CVImportResult {
  message: string
  user_id: number
  competencies_assigned: number
  extracted_info?: Record<string, any>
  steps: CVImportStep[]
  warnings: string[]
}

// ─── Pipeline steps définition (ordre fixe pour le stepper) ──────────────────
const PIPELINE_STEPS: CVImportStep[] = [
  { step: 'download',     label: 'Téléchargement du document',         status: 'pending' },
  { step: 'llm_parse',    label: 'Analyse IA — Extraction du profil',  status: 'pending' },
  { step: 'user_resolve', label: 'Résolution & création d\'identité',  status: 'pending' },
  { step: 'competencies', label: 'Mapping des compétences RAG',         status: 'pending' },
  { step: 'missions',     label: 'Extraction & indexation des missions',status: 'pending' },
  { step: 'embedding',    label: 'Génération des embeddings vectoriels',status: 'pending' },
  { step: 'db_save',      label: 'Sauvegarde en base de données',       status: 'pending' },
]

// ─── State ────────────────────────────────────────────────────────────────────
const cvUrl = ref('')
const loading = ref(false)
const error = ref('')
const errorType = ref<'network' | 'ai' | 'identity' | 'generic' | ''>('')
const successData = ref<CVImportResult | null>(null)
const googleClientId = ref('')
const tokenClient = ref<any>(null)

// Stepper animé
const displayedSteps = ref<CVImportStep[]>(PIPELINE_STEPS.map(s => ({ ...s })))
const currentRunningIndex = ref(-1)
let stepTimerHandle: ReturnType<typeof setTimeout> | null = null

// ─── Google OAuth ─────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const res = await axios.get('/auth/google/config')
    if (res.data.client_id) {
      googleClientId.value = res.data.client_id
      initGoogleClient()
    }
  } catch {
    console.warn('Impossible de récupérer la configuration Google ID')
  }
})

const initGoogleClient = () => {
  if (!(window as any).google) return
  tokenClient.value = (window as any).google.accounts.oauth2.initTokenClient({
    client_id: googleClientId.value,
    scope: 'https://www.googleapis.com/auth/documents.readonly https://www.googleapis.com/auth/drive.readonly',
    callback: (response: any) => {
      if (response.error !== undefined) throw response
      executeImport(response.access_token)
    },
  })
}

const handlePrivateImport = () => {
  if (!cvUrl.value) { error.value = "Veuillez d'abord renseigner le lien du Google Doc."; return }
  error.value = ''
  if (!tokenClient.value && googleClientId.value) initGoogleClient()
  if (!tokenClient.value) {
    error.value = !googleClientId.value
      ? "Configuration Google ID manquante. Vérifiez que 'source secrets.sh' a bien été exécuté avant 'docker-compose up'."
      : "Le script d'authentification Google est introuvable (bloqué par un bloqueur de pub ?)"
    return
  }
  loading.value = true
  tokenClient.value.requestAccessToken()
}

const submitCV = async () => { if (!cvUrl.value) return; await executeImport() }

// ─── Stepper simulation ───────────────────────────────────────────────────────
const resetStepper = () => {
  displayedSteps.value = PIPELINE_STEPS.map(s => ({ ...s }))
  currentRunningIndex.value = -1
  if (stepTimerHandle) { clearTimeout(stepTimerHandle); stepTimerHandle = null }
}

const advanceSimulatedStep = () => {
  const next = currentRunningIndex.value + 1
  if (next >= displayedSteps.value.length) return
  // Mark previous as running → success (optimistic)
  if (currentRunningIndex.value >= 0) {
    displayedSteps.value[currentRunningIndex.value].status = 'success'
  }
  currentRunningIndex.value = next
  displayedSteps.value[next].status = 'running'

  // LLM step takes longer — schedule next advance with varying delays
  const delays = [800, 12000, 2500, 3000, 1500, 2000, 1000]
  const delay = delays[next] ?? 1500
  stepTimerHandle = setTimeout(advanceSimulatedStep, delay)
}

const applyRealSteps = (steps: CVImportStep[]) => {
  if (stepTimerHandle) { clearTimeout(stepTimerHandle); stepTimerHandle = null }
  // Map real steps onto displayedSteps by step key
  for (const real of steps) {
    const idx = displayedSteps.value.findIndex(s => s.step === real.step)
    if (idx !== -1) {
      displayedSteps.value[idx] = { ...real }
    }
  }
  // Mark any remaining pending steps as skipped
  displayedSteps.value = displayedSteps.value.map(s =>
    s.status === 'pending' || s.status === 'running' ? { ...s, status: 'skipped' } : s
  )
  currentRunningIndex.value = displayedSteps.value.length
}

// ─── Error categorization ─────────────────────────────────────────────────────
const categorizeError = (err: any): void => {
  const detail: string = err.response?.data?.detail || ''
  const status: number = err.response?.status || 0

  if (status === 0 || !err.response) {
    errorType.value = 'network'
    error.value = "Impossible de joindre le serveur. Vérifiez votre connexion réseau."
  } else if (detail.toLowerCase().includes('not a cv') || detail.toLowerCase().includes('resume')) {
    errorType.value = 'ai'
    error.value = "Ce document n'a pas été reconnu comme un CV par l'IA Gemini. Vérifiez le contenu du fichier."
  } else if (detail.toLowerCase().includes('llm') || detail.toLowerCase().includes('gemini') || status === 500) {
    errorType.value = 'ai'
    error.value = `Erreur lors de l'analyse IA : ${detail || 'service Gemini temporairement indisponible.'}`
  } else if (detail.toLowerCase().includes('refusé') || detail.toLowerCase().includes('accès') || status === 403 || status === 401) {
    errorType.value = 'identity'
    error.value = "Accès refusé au document. Utilisez le bouton 'Importer avec mon compte Google'."
  } else if (detail.toLowerCase().includes('user creation') || detail.toLowerCase().includes('identity')) {
    errorType.value = 'identity'
    error.value = `Erreur d'identité : ${detail}`
  } else if (status === 400) {
    errorType.value = 'generic'
    error.value = detail || "Lien invalide ou document inaccessible."
  } else {
    errorType.value = 'generic'
    error.value = detail || "Erreur lors de l'analyse du CV. Vérifiez le lien."
  }

  // Mark the last running step as error
  const runningIdx = displayedSteps.value.findIndex(s => s.status === 'running')
  if (runningIdx !== -1) displayedSteps.value[runningIdx].status = 'error'
}

const errorIcon = computed(() => {
  if (errorType.value === 'network') return '🌐'
  if (errorType.value === 'ai') return '🤖'
  if (errorType.value === 'identity') return '🔐'
  return '⚠️'
})

// ─── Main import function ─────────────────────────────────────────────────────
const executeImport = async (googleToken?: string) => {
  loading.value = true
  error.value = ''
  errorType.value = ''
  successData.value = null
  resetStepper()

  // Start simulated stepper after short delay
  stepTimerHandle = setTimeout(advanceSimulatedStep, 300)

  try {
    const payload: any = { url: cvUrl.value }
    if (googleToken) payload.google_access_token = googleToken

    const response = await axios.post('/api/cv/import', payload, {
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    successData.value = response.data
    applyRealSteps(response.data.steps || [])
    cvUrl.value = ''
  } catch (err: any) {
    console.error(err)
    categorizeError(err)
  } finally {
    loading.value = false
  }
}

const stepStatusIcon = (status: string) => {
  if (status === 'success') return '✓'
  if (status === 'warning') return '⚠'
  if (status === 'error') return '✕'
  if (status === 'running') return '…'
  if (status === 'skipped') return '–'
  return '○'
}
</script>

<template>
  <div class="import-wrapper fade-in">
    <div class="header-section">
      <div class="title-wrapper">
        <FileDown class="icon-title" size="32" />
        <h2>Import CV (RAG)</h2>
      </div>
      <p class="subtitle">Scannez un profil via l'Intelligence Artificielle de Google Gemini</p>
    </div>

    <div class="reader-card glass-panel">
      <div class="card-header">
        <h3>Analyser un Google Doc</h3>
      </div>

      <div class="card-body">
        <!-- Form -->
        <form @submit.prevent="submitCV" class="import-form">
          <div class="form-group">
            <label>Lien Public du Google Doc</label>
            <input
              v-model="cvUrl"
              type="url"
              required
              class="glass-input"
              placeholder="https://docs.google.com/document/d/.../edit"
              :disabled="loading"
              aria-label="URL du Google Doc CV"
            />
            <small class="hint">Assurez-vous que le lien est réglé sur "Tous les utilisateurs disposant du lien".</small>
          </div>

          <div class="actions-group">
            <button type="submit" class="submit-btn" :disabled="loading || !cvUrl" aria-label="Scanner le CV en mode public">
              <RefreshCw v-if="loading" size="18" class="spin" />
              <span v-else>Scanner &amp; Intégrer (Public)</span>
            </button>
            <button
              type="button"
              @click="handlePrivateImport"
              class="submit-btn private-btn"
              :disabled="loading"
              title="Autoriser l'accès à ce document privé via Google"
              aria-label="Importer avec authentification Google"
            >
              <Lock size="18" />
              <span>Importer avec mon compte Google</span>
            </button>
          </div>
        </form>

        <!-- ── Pipeline Stepper ──────────────────────────────────────────── -->
        <div class="pipeline-stepper" :class="{ active: loading || successData || error }">
          <div class="stepper-title">
            <span v-if="loading" class="stepper-label-active pulse-text">Analyse en cours…</span>
            <span v-else-if="successData" class="stepper-label-done">Pipeline terminé</span>
            <span v-else-if="error" class="stepper-label-error">Analyse interrompue</span>
            <span v-else class="stepper-label-idle">Étapes du pipeline IA</span>
          </div>

          <div class="steps-list">
            <div
              v-for="(step, idx) in displayedSteps"
              :key="step.step"
              class="step-item"
              :class="`step-${step.status}`"
            >
              <div class="step-indicator">
                <div class="step-icon">
                  <span v-if="step.status === 'running'" class="dot-spinner"></span>
                  <span v-else class="status-char">{{ stepStatusIcon(step.status) }}</span>
                </div>
                <div v-if="idx < displayedSteps.length - 1" class="step-connector" :class="`conn-${step.status}`"></div>
              </div>
              <div class="step-content">
                <div class="step-label">{{ step.label }}</div>
                <div v-if="step.detail && step.status !== 'pending'" class="step-detail">{{ step.detail }}</div>
                <div v-if="step.duration_ms" class="step-duration">{{ step.duration_ms }}ms</div>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Warnings ───────────────────────────────────────────────────── -->
        <div v-if="successData?.warnings?.length" class="warnings-panel">
          <div class="warnings-header">
            <AlertTriangle size="16" />
            <span>{{ successData.warnings.length }} avertissement(s) non-bloquant(s)</span>
          </div>
          <ul class="warnings-list">
            <li v-for="(w, i) in successData.warnings" :key="i">{{ w }}</li>
          </ul>
        </div>

        <!-- ── Error ──────────────────────────────────────────────────────── -->
        <div v-if="error" class="alert-box error fade-in-up">
          <span class="error-icon-emoji">{{ errorIcon }}</span>
          <div class="error-content">
            <strong>Erreur d'analyse</strong>
            <p>{{ error }}</p>
          </div>
        </div>

        <!-- ── Success ────────────────────────────────────────────────────── -->
        <div v-if="successData" class="alert-box success fade-in-up">
          <CheckCircle size="24" class="success-icon" />
          <div class="success-content">
            <h4>Analyse Terminée</h4>
            <p>{{ successData.message }}</p>
            <div class="badges">
              <span class="badge user">👤 User ID #{{ successData.user_id }}</span>
              <span class="badge comp">⭐ {{ successData.competencies_assigned }} Compétences Vectorisées</span>
              <span v-if="successData.extracted_info?.is_anonymous" class="badge anon">🔒 Anonyme</span>
            </div>
            <RouterLink :to="{ name: 'user-detail', params: { id: successData.user_id } }" class="view-btn">
              Voir la fiche du Consultant
            </RouterLink>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.import-wrapper {
  max-width: 800px;
  margin: 0 auto;
  padding: 40px 20px;
}
.header-section { text-align: center; margin-bottom: 30px; }
.title-wrapper {
  display: flex; align-items: center; justify-content: center;
  gap: 16px; margin-bottom: 12px;
}
h2 { font-size: 36px; font-weight: 800; color: #1a1a1a; letter-spacing: -1px; }
.icon-title { color: #E31937; }
.subtitle { color: #475569; font-size: 18px; }

.glass-panel {
  background: rgba(255,255,255,0.95);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 16px;
  box-shadow: 0 20px 40px rgba(0,0,0,0.1);
  overflow: hidden;
}
.card-header {
  padding: 20px 30px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  background: rgba(250,250,250,0.9);
}
.card-header h3 { font-size: 20px; font-weight: 700; color: #1A1A1A; margin: 0; }
.card-body { padding: 30px; display: flex; flex-direction: column; gap: 24px; }

.import-form { display: flex; flex-direction: column; gap: 20px; }
.form-group { display: flex; flex-direction: column; gap: 8px; }
label { font-weight: 600; color: #333; }
.glass-input {
  width: 100%; padding: 14px 16px;
  border: 2px solid #ddd; border-radius: 12px;
  background: #fdfdfd; font-size: 15px; transition: all 0.2s; color: #1A1A1A;
  box-sizing: border-box;
}
.glass-input:focus { outline: none; border-color: #E31937; background: #fff; box-shadow: 0 0 0 4px rgba(227,25,55,0.25); }
.glass-input:disabled { opacity: 0.6; cursor: not-allowed; }
.hint { color: #777; font-size: 13px; }

.actions-group { display: flex; gap: 16px; }
.submit-btn {
  background: #111; color: #fff; border: none; border-radius: 12px;
  padding: 14px 24px; font-size: 16px; font-weight: 600; cursor: pointer;
  transition: all 0.2s; display: flex; justify-content: center; align-items: center; gap: 8px; flex: 1;
}
.private-btn { background: transparent; color: #E31937; border: 2px solid #E31937; }
.private-btn:hover:not(:disabled) { background: #E31937; color: #fff; }
.submit-btn:hover:not(:disabled) { background: #000; transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,0.15); }
.submit-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* ── Pipeline Stepper ──────────────────────────────────────── */
.pipeline-stepper {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 20px;
  transition: all 0.3s;
}
.pipeline-stepper.active { border-color: #cbd5e1; background: #f1f5f9; }

.stepper-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8; margin-bottom: 16px; }
.stepper-label-active { color: #E31937; }
.stepper-label-done { color: #16a34a; }
.stepper-label-error { color: #dc2626; }
.stepper-label-idle { color: #94a3b8; }
.pulse-text { animation: pulse-text 1.5s ease-in-out infinite; }
@keyframes pulse-text { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

.steps-list { display: flex; flex-direction: column; }
.step-item { display: flex; gap: 12px; }

.step-indicator { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; }
.step-icon {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; flex-shrink: 0;
  transition: all 0.3s;
}
.step-pending .step-icon  { background: #e2e8f0; color: #94a3b8; }
.step-running .step-icon  { background: #dbeafe; color: #2563eb; box-shadow: 0 0 0 4px rgba(37,99,235,0.15); }
.step-success .step-icon  { background: #dcfce7; color: #16a34a; }
.step-warning .step-icon  { background: #fef3c7; color: #d97706; }
.step-error .step-icon    { background: #fee2e2; color: #dc2626; }
.step-skipped .step-icon  { background: #f1f5f9; color: #cbd5e1; }

.step-connector {
  width: 2px; flex: 1; min-height: 12px; margin: 2px 0;
  background: #e2e8f0; transition: background 0.4s;
}
.conn-success { background: #86efac; }
.conn-warning { background: #fde68a; }
.conn-error   { background: #fca5a5; }
.conn-running { background: linear-gradient(to bottom, #93c5fd, #e2e8f0); }

.step-content { padding: 2px 0 14px; flex: 1; }
.step-label { font-size: 13px; font-weight: 600; color: #1e293b; }
.step-pending .step-label, .step-skipped .step-label { color: #94a3b8; }
.step-detail { font-size: 11px; color: #64748b; margin-top: 2px; font-family: 'Fira Code', monospace; }
.step-duration { font-size: 10px; color: #94a3b8; margin-top: 1px; }

/* Dot spinner for running */
.dot-spinner {
  display: inline-block; width: 10px; height: 10px;
  border: 2px solid #2563eb; border-top-color: transparent;
  border-radius: 50%; animation: spin 0.7s linear infinite;
}

/* ── Warnings ──────────────────────────────────────────────── */
.warnings-panel {
  background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px; padding: 14px 16px;
}
.warnings-header {
  display: flex; align-items: center; gap: 8px;
  font-weight: 700; font-size: 13px; color: #92400e; margin-bottom: 8px;
}
.warnings-list { margin: 0; padding-left: 20px; }
.warnings-list li { font-size: 12px; color: #78350f; margin-bottom: 4px; line-height: 1.5; }

/* ── Alert boxes ───────────────────────────────────────────── */
.alert-box {
  border-radius: 12px; display: flex; gap: 16px; padding: 20px;
}
.alert-box.error {
  background: #fff0f0; color: #d32f2f;
  border: 1px solid #ffcdd2; align-items: flex-start;
}
.error-icon-emoji { font-size: 22px; flex-shrink: 0; margin-top: 2px; }
.error-content strong { display: block; font-size: 14px; margin-bottom: 4px; }
.error-content p { margin: 0; font-size: 13px; line-height: 1.5; }

.alert-box.success { background: #f0fdf4; border: 1px solid #bbf7d0; align-items: flex-start; }
.success-icon { color: #16a34a; flex-shrink: 0; margin-top: 2px; }
.success-content h4 { margin: 0 0 8px 0; color: #166534; font-size: 18px; }
.success-content p { color: #15803d; margin: 0 0 16px 0; }

.badges { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.badge { padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; }
.badge.user { background: #dbeafe; color: #1e40af; }
.badge.comp { background: #ffedd5; color: #c2410c; }
.badge.anon { background: #f0f0f0; color: #555; }

.view-btn {
  display: inline-block; background: #16a34a; color: #fff;
  text-decoration: none; padding: 10px 20px; border-radius: 8px;
  font-weight: 600; font-size: 14px; transition: all 0.2s;
}
.view-btn:hover { background: #15803d; transform: translateY(-1px); }

/* ── Animations ────────────────────────────────────────────── */
.spin { animation: spin 1s infinite linear; }
@keyframes spin { to { transform: rotate(360deg); } }
.fade-in { animation: fadeIn 0.4s ease-out; }
.fade-in-up { animation: fadeInUp 0.4s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
</style>
