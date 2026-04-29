<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import axios from 'axios'
import PageHeader from '../components/ui/PageHeader.vue'
import {
  BarChart3, RefreshCcw, Loader2, CheckCircle2, AlertCircle,
  AlertTriangle, Zap, Database, Brain, FileText, Clock,
  TrendingUp, ShieldCheck, Activity, FolderOpen, ArrowRight,
  Users, Link
} from 'lucide-vue-next'


// ── Types ────────────────────────────────────────────────────────────────────

interface DqMetric {
  ok: number
  total: number
  pct: number
  status: 'ok' | 'warning' | 'error'
}

interface DqReport {
  computed_at: string
  total_cvs: number
  users_with_cv: number
  score: number
  grade: 'A' | 'B' | 'C' | 'D'
  metrics: Record<string, DqMetric>
  issues: string[]
  recommendation: string
}

interface ScoringStatus {
  status: 'idle' | 'running' | 'uploading' | 'batch_running' | 'applying' | 'completed' | 'error'
  total_users?: number
  processed?: number
  success?: number
  error_count?: number
  errors?: string[]
  logs?: string[]
  batch_job_id?: string
  dest_uri?: string
  error?: string
  start_time?: string
}

interface DriveIngestionKPI { value: number; pct: number; ok: number; total: number; status: string; unit: string }
interface DriveStats {
  total_files: number; imported: number; errors: number
  pending: number; queued: number; processing: number
  freshness_hours: number | null
  metrics: Record<string, DriveIngestionKPI>
  score: number; grade: string
  issues: string[]; recommendation: string; computed_at: string
}

interface IssueAction {
  label: string
  to: string
}

// ── State ────────────────────────────────────────────────────────────────────

const dqReport = ref<DqReport | null>(null)
const dqLoading = ref(false)
const dqError = ref('')

const scoringStatus = ref<ScoringStatus>({ status: 'idle' })
const scoringLoading = ref(false)

const driveStats = ref<DriveStats | null>(null)
const driveLoading = ref(false)

const lastRefreshDate = ref<Date | null>(null)
const relativeTime = ref('')
let pollId: ReturnType<typeof setInterval>
let clockId: ReturnType<typeof setInterval>

// ── Computed ─────────────────────────────────────────────────────────────────

const gradeColor = computed(() => {
  const map: Record<string, string> = { A: '#10b981', B: '#3b82f6', C: '#f59e0b', D: '#ef4444' }
  return map[dqReport.value?.grade ?? 'D'] ?? '#ef4444'
})

const driveGradeColor = computed(() => {
  const g = driveStats.value?.grade ?? 'F'
  if (g === 'A') return '#10b981'
  if (g === 'B') return '#3b82f6'
  if (g === 'C') return '#f59e0b'
  if (g === 'D') return '#ea580c'
  return '#ef4444'
})

const scoringPct = computed(() => {
  const s = scoringStatus.value
  if (!s.total_users || !s.processed) return 0
  return Math.min(100, Math.round((s.processed / s.total_users) * 100))
})

// SVG ring for global score
const svgRingPath = computed(() => {
  const score = dqReport.value?.score ?? 0
  const r = 42
  const circumference = 2 * Math.PI * r
  const dashOffset = circumference - (score / 100) * circumference
  return { r, circumference, dashOffset }
})

const metricLabels: Record<string, string> = {
  missions: 'Missions',
  embedding: 'Embeddings',
  competencies: 'Compétences extraites',
  summary: 'Résumé',
  current_role: 'Poste actuel',
  competency_assignment: 'Compétences assignées',
  ai_scoring: 'Scoring IA (≥10)',
}

const driveMetricIcons: Record<string, any> = {
  'Taux d\'import réussi': CheckCircle2,
  'Taux sans erreur': CheckCircle2,
  'Nommage correct': FileText,
  'Liaison consultant': Users,
  'Qualité du traitement': Clock,
}

const metricIcons: Record<string, any> = {
  missions: FileText,
  embedding: Brain,
  competencies: TrendingUp,
  summary: FileText,
  current_role: Database,
  competency_assignment: Users,
  ai_scoring: Zap,
}

// ── Issue CTA mapping ─────────────────────────────────────────────────────────

const issueAction = (issue: string): IssueAction | null => {
  const lc = issue.toLowerCase()
  if (lc.includes('retry apply') || lc.includes('bulk apply') || lc.includes('compétence') || lc.includes('aucune compétence')) {

    return { label: 'Retry Apply', to: '/admin/bulk-import' }
  }
  if (lc.includes('drive') || lc.includes('ingestion') || lc.includes('nommage')) {
    return { label: 'Dashboard Drive', to: '/admin/drive-ingestion' }
  }
  if (lc.includes('embedding')) {
    return { label: 'Voir Admin', to: '/admin/bulk-import' }
  }
  return null
}

// ── Actions ──────────────────────────────────────────────────────────────────

const fetchDq = async () => {
  dqLoading.value = true
  dqError.value = ''
  try {
    const token = localStorage.getItem('token') || localStorage.getItem('access_token') || ''
    const res = await axios.get('/api/cv/bulk-reanalyse/data-quality', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    dqReport.value = res.data
  } catch (e: any) {
    dqError.value = e.response?.data?.detail || e.message
  } finally {
    dqLoading.value = false
  }
}

const fetchScoring = async () => {
  scoringLoading.value = true
  try {
    const res = await axios.get('/api/competencies/bulk-scoring-all/status')
    scoringStatus.value = res.data
  } catch (e) {
    console.error('scoring status fetch failed', e)
  } finally {
    scoringLoading.value = false
  }
}

const resumeFromGcs = async () => {
  try {
    const res = await axios.post('/api/competencies/bulk-scoring-all/resume/manual')
    const action = res.data?.action
    if (action === 'apply_triggered') {
      alert('✅ Reprise lancée depuis GCS — les scores vont être écrits en base. La progression apparaîtra dans quelques secondes.')
    } else if (action === 'noop') {
      alert(`ℹ️ Aucune action nécessaire (${res.data?.reason || 'job non actif'}).`)
    } else if (action === 'error') {
      alert(`❌ Le job Vertex a échoué côté GCP (state=${res.data?.state}).`)
    } else {
      alert(`Job en cours (${res.data?.state || 'état inconnu'}) — réessayez dans quelques minutes.`)
    }
    await fetchScoring()
  } catch (e: any) {
    alert(`Erreur lors de la reprise : ${e.response?.data?.detail || e.message}`)
  }
}

const fetchDriveStats = async () => {
  driveLoading.value = true
  try {
    const token = localStorage.getItem('token') || localStorage.getItem('access_token') || ''
    const res = await axios.get('/api/drive/ingestion/stats', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    driveStats.value = res.data
  } catch (e) {
    console.error('drive stats fetch failed', e)
  } finally {
    driveLoading.value = false
  }
}

const updateRelativeTime = () => {
  if (!lastRefreshDate.value) { relativeTime.value = ''; return }
  const diffMs = Date.now() - lastRefreshDate.value.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffSec = Math.floor((diffMs % 60000) / 1000)
  if (diffMin === 0) {
    relativeTime.value = diffSec < 5 ? 'à l\'instant' : `il y a ${diffSec}s`
  } else {
    relativeTime.value = `il y a ${diffMin} min`
  }
}

const refresh = async () => {
  await Promise.all([fetchDq(), fetchScoring(), fetchDriveStats()])
  lastRefreshDate.value = new Date()
  updateRelativeTime()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(() => {
  refresh()
  pollId = setInterval(refresh, 30000)
  clockId = setInterval(updateRelativeTime, 5000)
})

onUnmounted(() => {
  clearInterval(pollId)
  clearInterval(clockId)
})

// ── Utils ─────────────────────────────────────────────────────────────────────

const fmt = (n?: number) => (n ?? 0).toLocaleString('fr-FR')
const fmtDate = (s: string) => new Date(s).toLocaleString('fr-FR')
</script>

<template>
  <div class="dq-view fade-in">
    <PageHeader
      title="Data Quality Dashboard"
      subtitle="Supervision globale de la qualité des pipelines de données"
    />

    <!-- Refresh toolbar -->
    <div class="toolbar">
      <button class="btn btn-refresh" @click="refresh" :disabled="dqLoading || scoringLoading" aria-label="Rafraîchir tous les indicateurs">
        <Loader2 v-if="dqLoading || scoringLoading" :size="16" class="spin" />
        <RefreshCcw v-else :size="16" />
        Rafraîchir
      </button>
      <span v-if="lastRefreshDate" class="computed-at">
        <div class="live-dot" :class="{ pulsing: dqLoading || scoringLoading }" />
        Mis à jour {{ relativeTime }}
      </span>
      <span v-else-if="dqReport" class="computed-at">
        <Clock :size="13" /> Calculé le {{ fmtDate(dqReport.computed_at) }}
      </span>
      <span class="auto-refresh-badge">Auto ↻ 30s</span>
    </div>

    <!-- Error -->
    <div v-if="dqError" class="alert alert-error">
      <AlertCircle :size="16" /> {{ dqError }}
    </div>

    <!-- ── GLOBAL SCORE HERO ── -->
    <div v-if="dqReport" class="score-hero" role="status" aria-live="polite">
      <!-- SVG Ring Score -->
      <div class="score-ring-wrap">
        <svg class="score-ring" viewBox="0 0 100 100" aria-hidden="true">
          <circle
            cx="50" cy="50"
            :r="svgRingPath.r"
            fill="none"
            stroke="#e2e8f0"
            stroke-width="8"
          />
          <circle
            cx="50" cy="50"
            :r="svgRingPath.r"
            fill="none"
            :stroke="gradeColor"
            stroke-width="8"
            stroke-linecap="round"
            :stroke-dasharray="svgRingPath.circumference"
            :stroke-dashoffset="svgRingPath.dashOffset"
            class="ring-fill"
            transform="rotate(-90 50 50)"
          />
        </svg>
        <div class="ring-grade" :style="{ color: gradeColor }">{{ dqReport.grade }}</div>
      </div>

      <!-- Score info -->
      <div class="score-info">
        <div class="score-value">{{ dqReport.score }}<span class="score-max">/100</span></div>
        <div class="score-sub">{{ fmt(dqReport.total_cvs) }} CVs · {{ fmt(dqReport.users_with_cv) }} consultants</div>
        <div class="score-label">Score Data Quality Global</div>
      </div>

      <!-- Status pill -->
      <div class="score-pills">
        <div
          class="status-pill"
          :class="dqReport.issues.length === 0 ? 'pill-ok' : 'pill-warn pill-pulse'"
        >
          <ShieldCheck v-if="dqReport.issues.length === 0" :size="14" />
          <AlertTriangle v-else :size="14" />
          {{ dqReport.issues.length === 0 ? 'Pipeline sain' : `${dqReport.issues.length} anomalie(s)` }}
        </div>
        <RouterLink
          v-if="dqReport.issues.length > 0"
          to="/admin/bulk-import"
          class="hero-detail-link"
        >
          Voir actions <ArrowRight :size="12" />
        </RouterLink>
      </div>
    </div>
    <div v-else-if="dqLoading" class="loading-placeholder">
      <Loader2 :size="28" class="spin" /> Analyse en cours…
    </div>

    <!-- ── MÉTRIQUES CV PIPELINE ── -->
    <div v-if="dqReport" class="card">
      <div class="card-header">
        <Database :size="18" class="icon-blue" />
        <span>Pipeline CV — Qualité des données extraites</span>
      </div>
      <div class="metrics-list">
        <div
          v-for="(metric, key) in dqReport.metrics"
          :key="key"
          class="metric-row"
        >
          <div class="metric-label">
            <component :is="metricIcons[key] ?? BarChart3" :size="14" class="metric-icon" :class="`status-${metric.status}`" />
            {{ metricLabels[key] ?? key }}
          </div>
          <div class="bar-wrap">
            <div class="bar-fill" :class="`bar-${metric.status}`" :style="{ width: metric.pct + '%' }" />
          </div>
          <div class="metric-pct" :class="`pct-${metric.status}`">{{ metric.pct }}%</div>
          <div class="metric-count">
            <template v-if="key === 'ai_scoring' && (metric as any).avg_scored_per_user != null">
              moy. {{ (metric as any).avg_scored_per_user }}/consultant
            </template>
            <template v-else>{{ fmt(metric.ok) }}/{{ fmt(metric.total) }}</template>
          </div>
          <div class="metric-badge" :class="`badge-${metric.status}`">
            <CheckCircle2 v-if="metric.status === 'ok'" :size="12" />
            <AlertTriangle v-else-if="metric.status === 'warning'" :size="12" />
            <AlertCircle v-else :size="12" />
          </div>
        </div>
      </div>

      <!-- Issues actionnables -->
      <div v-if="dqReport.issues.length > 0" class="issues-box">
        <div v-for="issue in dqReport.issues" :key="issue" class="issue-line">
          <AlertTriangle :size="13" class="issue-icon" />
          <span class="issue-text">{{ issue }}</span>
          <RouterLink
            v-if="issueAction(issue)"
            :to="issueAction(issue)!.to"
            class="issue-cta"
          >
            {{ issueAction(issue)!.label }} <ArrowRight :size="11" />
          </RouterLink>
        </div>
      </div>
      <div v-else class="all-ok">
        <CheckCircle2 :size="16" /> {{ dqReport.recommendation }}
      </div>
    </div>

    <!-- ── SCORING IA COMPÉTENCES ── -->
    <div class="card">
      <div class="card-header">
        <Zap :size="18" class="icon-amber" />
        <span>Scoring IA — Couverture des Compétences</span>
      </div>

      <!-- SOUS-SECTION : Qualité Data (KPI) -->
      <div class="scoring-section-label"><BarChart3 :size="12" /> Qualité Data</div>

      <!-- Couverture réelle (source: dqReport.metrics.ai_scoring) -->
      <div v-if="dqReport?.metrics?.ai_scoring" class="scoring-coverage">
        <div class="cov-main">
          <div class="cov-numbers">
            <span class="cov-ok">{{ fmt((dqReport.metrics.ai_scoring as any).ok) }}</span>
            <span class="cov-sep">/</span>
            <span class="cov-total">{{ fmt((dqReport.metrics.ai_scoring as any).total) }}</span>
          </div>
          <div class="cov-label">consultants avec ≥ {{ (dqReport.metrics.ai_scoring as any).min_scored_count ?? 10 }} compétences scorées par l'IA</div>
          <div class="cov-avg" v-if="(dqReport.metrics.ai_scoring as any).avg_scored_per_user">
            Moyenne : <strong>{{ (dqReport.metrics.ai_scoring as any).avg_scored_per_user }}</strong> compétences scorées / consultant
          </div>
        </div>
        <div class="cov-gauge">
          <div class="cov-bar-track">
            <div
              class="cov-bar-fill"
              :class="`cov-bar-${(dqReport.metrics.ai_scoring as any).status}`"
              :style="{ width: (dqReport.metrics.ai_scoring as any).pct + '%' }"
            />
          </div>
          <div class="cov-pct" :class="`cov-pct-${(dqReport.metrics.ai_scoring as any).status}`">
            {{ (dqReport.metrics.ai_scoring as any).pct }}%
          </div>
        </div>
        <div v-if="(dqReport.metrics.ai_scoring as any).status !== 'ok'" class="cov-action">
          <AlertTriangle :size="14" />
          <span>{{ (dqReport.metrics.ai_scoring as any).total - (dqReport.metrics.ai_scoring as any).ok }} consultant(s) n'ont pas encore atteint le seuil</span>
        </div>

        <div v-else class="cov-action cov-action-ok">
          <CheckCircle2 :size="14" /> Tous les consultants ont atteint le seuil de qualité IA
        </div>
      </div>
      <div v-else-if="dqLoading" class="scoring-idle"><Loader2 :size="16" class="spin" /> Calcul en cours…</div>
      <div v-else class="scoring-idle"><Activity :size="16" /> Données de scoring non disponibles — rafraîchir pour recalculer.</div>

      <!-- SOUS-SECTION : Dernier Run (process monitoring) -->
      <div class="scoring-section-label" style="border-top: 1px solid rgba(255,255,255,0.06); margin-top: 0;"><Activity :size="12" /> Dernier Run</div>
      <div class="scoring-run-status">
        <div class="run-info">
          <!-- Badge statut -->
          <div class="run-badge" :class="`run-${scoringStatus.status}`">
            <Loader2 v-if="['running','uploading','batch_running','applying'].includes(scoringStatus.status)" :size="12" class="spin" />
            <CheckCircle2 v-else-if="scoringStatus.status === 'completed'" :size="12" />
            <AlertCircle v-else-if="scoringStatus.status === 'error'" :size="12" />
            <Activity v-else :size="12" />
            <span v-if="scoringStatus.status === 'idle'">En veille</span>
            <span v-else-if="scoringStatus.status === 'uploading'">📤 Upload JSONL → GCS…</span>
            <span v-else-if="scoringStatus.status === 'batch_running'">⚡ Job Vertex AI en cours…</span>
            <span v-else-if="scoringStatus.status === 'applying'">💾 Écriture des scores en DB…</span>
            <span v-else-if="scoringStatus.status === 'running'">{{ fmt(scoringStatus.processed) }}/{{ fmt(scoringStatus.total_users) }} en cours</span>
            <span v-else-if="scoringStatus.status === 'completed'">✅ {{ fmt(scoringStatus.success) }} scores appliqués / {{ fmt(scoringStatus.total_users) }} users</span>
            <span v-else-if="scoringStatus.status === 'error'">❌ Erreur pipeline</span>
            <span v-else>En veille</span>
          </div>

          <!-- Batch job ID -->
          <div v-if="scoringStatus.batch_job_id" class="run-job-id">
            <span class="run-job-label">Job Vertex :</span>
            <code class="run-job-code">{{ scoringStatus.batch_job_id?.split('/').pop() }}</code>
          </div>

          <!-- Erreur -->
          <div v-if="scoringStatus.error" class="run-error-msg">
            <AlertCircle :size="12" /> {{ scoringStatus.error }}
          </div>

          <!-- Logs pipeline (3 dernières étapes) -->
          <div v-if="scoringStatus.logs && scoringStatus.logs.length > 0" class="run-logs">
            <div class="run-logs-label">Dernières étapes :</div>
            <div
              v-for="(log, i) in scoringStatus.logs.slice(-4).reverse()"
              :key="i"
              class="run-log-line"
              :class="{ 'run-log-active': i === 0 }"
            >
              <span class="run-log-dot" :class="i === 0 ? 'dot-active' : 'dot-done'" />
              {{ log }}
            </div>
          </div>

          <!-- Bouton Reprendre depuis GCS (visible si batch_running, error, ou completed avec erreurs bloquantes) -->
          <div
            v-if="scoringStatus.batch_job_id && (['batch_running', 'error'].includes(scoringStatus.status) || (scoringStatus.status === 'completed' && (scoringStatus.error_count || 0) > 0))"
            class="run-resume-wrap"
          >

            <button
              id="btn-resume-from-gcs"
              class="btn btn-resume"
              @click="resumeFromGcs"
              title="Reprendre l'application des résultats depuis GCS (si Vertex a terminé mais Cloud Run a été interrompu)"
            >
              ⚡ Reprendre depuis GCS
            </button>
            <span class="run-resume-hint">Poll Vertex + apply si SUCCEEDED</span>
          </div>
        </div>
        <RouterLink to="/admin/reanalysis" class="run-link">
          Voir Bulk Scoring <ArrowRight :size="12" />
        </RouterLink>
      </div>
    </div>

    <!-- ── DRIVE INGESTION KPIs ── -->
    <div class="card">
      <div class="card-header">
        <FolderOpen :size="18" class="icon-violet" />
        <span>Pipeline Drive — Ingestion des CVs</span>
        <RouterLink to="/admin/drive-ingestion" class="header-link">
          Dashboard complet <ArrowRight :size="13" />
        </RouterLink>
      </div>

      <div v-if="driveLoading && !driveStats" class="scoring-idle">
        <Loader2 :size="16" class="spin" /> Calcul des KPIs Drive…
      </div>

      <template v-else-if="driveStats">
        <!-- Grade + volumes -->
        <div class="drive-hero">
          <div class="drive-grade" :style="{ borderColor: driveGradeColor, color: driveGradeColor }">
            {{ driveStats.grade }}
          </div>
          <div class="drive-volumes">
            <div class="dv-item"><span class="dv-n">{{ fmt(driveStats.total_files) }}</span><span class="dv-l">Total</span></div>
            <div class="dv-item dv-ok"><span class="dv-n">{{ fmt(driveStats.imported) }}</span><span class="dv-l">Importés</span></div>
            <div class="dv-item dv-err"><span class="dv-n">{{ fmt(driveStats.errors) }}</span><span class="dv-l">Erreurs</span></div>
            <div class="dv-item"><span class="dv-n">{{ fmt(driveStats.pending + driveStats.queued) }}</span><span class="dv-l">En attente</span></div>
            <div class="dv-item" v-if="driveStats.freshness_hours !== null">
              <span class="dv-n" :class="driveStats.freshness_hours > 48 ? 'text-err' : driveStats.freshness_hours > 24 ? 'text-warn' : 'text-ok'">{{ driveStats.freshness_hours }}h</span>
              <span class="dv-l">Fraîcheur</span>
            </div>
          </div>
          <div class="drive-score">{{ driveStats.score }}<span class="drive-score-max">/100</span></div>
        </div>

        <!-- Métriques -->
        <div class="metrics-list">
          <div v-for="(metric, label) in driveStats.metrics" :key="label" class="metric-row drive-metric-row">
            <div class="metric-label">
              <component :is="driveMetricIcons[label as string] ?? BarChart3" :size="14" class="metric-icon" :class="`status-${metric.status === 'critical' ? 'error' : metric.status}`" />
              {{ label }}
            </div>
            <div class="bar-wrap">
              <div
                class="bar-fill"
                :class="metric.status === 'critical' ? 'bar-error' : metric.status === 'warning' ? 'bar-warning' : 'bar-ok'"
                :style="{ width: metric.pct + '%' }"
              />
            </div>
            <div class="metric-pct" :class="metric.status === 'critical' ? 'pct-error' : metric.status === 'warning' ? 'pct-warning' : 'pct-ok'">
              {{ metric.unit === 's' ? metric.value + 's' : metric.pct + '%' }}
            </div>
            <div class="metric-count">
              <template v-if="metric.unit !== 's'">{{ fmt(metric.ok) }}/{{ fmt(metric.total) }}</template>
              <template v-else>moy. {{ metric.value }}s</template>
            </div>
            <div class="metric-badge" :class="`badge-${metric.status === 'critical' ? 'error' : metric.status}`">
              <CheckCircle2 v-if="metric.status === 'ok'" :size="12" />
              <AlertTriangle v-else-if="metric.status === 'warning'" :size="12" />
              <AlertCircle v-else :size="12" />
            </div>
          </div>
        </div>

        <!-- Issues Drive actionnables -->
        <div v-if="driveStats.issues.length > 0" class="issues-box">
          <div v-for="issue in driveStats.issues" :key="issue" class="issue-line">
            <AlertTriangle :size="13" class="issue-icon" />
            <span class="issue-text">{{ issue }}</span>
            <RouterLink
              v-if="issueAction(issue)"
              :to="issueAction(issue)!.to"
              class="issue-cta"
            >
              {{ issueAction(issue)!.label }} <ArrowRight :size="11" />
            </RouterLink>
          </div>
        </div>
        <div v-else class="all-ok">
          <CheckCircle2 :size="16" /> {{ driveStats.recommendation }}
        </div>
      </template>

      <div v-else class="scoring-idle">
        <Activity :size="16" /> Données Drive non disponibles.
      </div>
    </div>

    <!-- ── PIPELINE GLOBALE — SYNTHÈSE ── -->
    <div class="card">
      <div class="card-header">
        <BarChart3 :size="18" class="icon-purple" />
        <span>Synthèse des Pipelines</span>
      </div>
      <div class="pipeline-grid">
        <!-- Pipeline CV -->
        <RouterLink to="/admin/bulk-import" class="pipeline-card pipeline-card-link">
          <div class="pc-icon" :class="dqReport ? `pc-icon-grade-${dqReport.grade.toLowerCase()}` : ''"><Database :size="22" /></div>
          <div class="pc-label">Pipeline CV (Vertex Batch)</div>
          <div class="pc-value" v-if="dqReport">{{ fmt(dqReport.total_cvs) }} CVs</div>
          <div class="pc-sub" v-if="dqReport">{{ fmt(dqReport.users_with_cv) }} consultants</div>
          <div class="pc-bar" v-if="dqReport">
            <div class="pc-bar-fill" :class="`grade-bar-${dqReport.grade.toLowerCase()}`" :style="{ width: dqReport.score + '%' }" />
          </div>
          <div class="pc-status" :class="dqReport ? `grade-${dqReport.grade.toLowerCase()}` : ''">
            Grade {{ dqReport?.grade ?? '—' }}
          </div>
        </RouterLink>

        <!-- Scoring IA -->
        <RouterLink to="/admin/reanalysis" class="pipeline-card pipeline-card-link">
          <div class="pc-icon" :class="scoringStatus.status === 'completed' ? 'pc-icon-grade-a' : scoringStatus.status === 'error' ? 'pc-icon-grade-d' : 'pc-icon-grade-b'"><Zap :size="22" /></div>
          <div class="pc-label">Scoring IA Compétences</div>
          <div class="pc-value" v-if="dqReport?.metrics?.ai_scoring">{{ (dqReport.metrics.ai_scoring as any).pct }}%</div>
          <div class="pc-sub" v-if="scoringStatus.status === 'completed'">
            {{ fmt(scoringStatus.success) }} / {{ fmt(scoringStatus.total_users) }}
          </div>
          <div class="pc-bar" v-if="dqReport?.metrics?.ai_scoring">
            <div class="pc-bar-fill" :class="`grade-bar-${(dqReport.metrics.ai_scoring as any).status === 'ok' ? 'a' : (dqReport.metrics.ai_scoring as any).status === 'warning' ? 'c' : 'd'}`" :style="{ width: (dqReport.metrics.ai_scoring as any).pct + '%' }" />
          </div>
          <div class="pc-status" :class="scoringStatus.status === 'completed' ? 'grade-a' : scoringStatus.status === 'error' ? 'grade-d' : 'grade-b'">
            {{ scoringStatus.status === 'completed' ? 'OK' : scoringStatus.status === 'running' ? 'En cours' : scoringStatus.status === 'error' ? 'Erreur' : 'Veille' }}
          </div>
        </RouterLink>

        <!-- Embeddings -->
        <RouterLink to="/admin/bulk-import" class="pipeline-card pipeline-card-link">
          <div class="pc-icon" :class="`pc-icon-grade-${dqReport?.metrics['embedding']?.status === 'ok' ? 'a' : dqReport?.metrics['embedding']?.status === 'warning' ? 'c' : 'd'}`"><Brain :size="22" /></div>
          <div class="pc-label">Embeddings Sémantiques</div>
          <div class="pc-value" v-if="dqReport">{{ dqReport.metrics['embedding']?.pct ?? 0 }}%</div>
          <div class="pc-sub" v-if="dqReport">{{ fmt(dqReport.metrics['embedding']?.ok) }} indexés</div>
          <div class="pc-bar" v-if="dqReport">
            <div class="pc-bar-fill" :class="`grade-bar-${dqReport?.metrics['embedding']?.status === 'ok' ? 'a' : dqReport?.metrics['embedding']?.status === 'warning' ? 'c' : 'd'}`" :style="{ width: (dqReport.metrics['embedding']?.pct ?? 0) + '%' }" />
          </div>
          <div class="pc-status" :class="`grade-${dqReport?.metrics['embedding']?.status === 'ok' ? 'a' : dqReport?.metrics['embedding']?.status === 'warning' ? 'c' : 'd'}`">
            {{ dqReport?.metrics['embedding']?.status === 'ok' ? 'Sain' : dqReport?.metrics['embedding']?.status === 'warning' ? 'Dégradé' : 'Critique' }}
          </div>
        </RouterLink>

        <!-- Drive -->
        <RouterLink to="/admin/drive-ingestion" class="pipeline-card pipeline-card-link">
          <div class="pc-icon" :class="driveStats ? `pc-icon-grade-${driveStats.grade.toLowerCase()}` : ''"><FolderOpen :size="22" /></div>
          <div class="pc-label">Drive Ingestion</div>
          <div class="pc-value" v-if="driveStats">{{ fmt(driveStats.imported) }} CVs</div>
          <div class="pc-sub" v-if="driveStats">Score {{ driveStats.score }}/100</div>
          <div class="pc-bar" v-if="driveStats">
            <div class="pc-bar-fill" :class="`grade-bar-${driveStats.grade.toLowerCase()}`" :style="{ width: driveStats.score + '%' }" />
          </div>
          <div class="pc-status" v-if="driveStats" :class="`grade-${driveStats.grade.toLowerCase()}`">
            Grade {{ driveStats.grade }}
          </div>
          <div class="pc-status grade-b" v-else>—</div>
        </RouterLink>
      </div>
    </div>

  </div>
</template>

<style scoped>
.dq-view {
  max-width: 960px;
  margin: 0 auto;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.fade-in {
  animation: fadeIn 0.35s ease forwards;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Toolbar */
.toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
}
.computed-at {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.78rem;
  color: #64748b;
}

/* Alerts */
.alert { display: flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; }
.alert-error { background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); color: #b91c1c; }

/* Score Hero */
.score-hero {
  background: rgba(255,255,255,0.85);
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 16px;
  padding: 2rem;
  display: flex;
  align-items: center;
  gap: 2rem;
  box-shadow: 0 4px 20px rgba(0,0,0,0.06);
}

/* SVG Ring */
.score-ring-wrap {
  position: relative;
  width: 100px;
  height: 100px;
  flex-shrink: 0;
}
.score-ring {
  width: 100px;
  height: 100px;
}
.ring-fill {
  transition: stroke-dashoffset 1s cubic-bezier(0.4, 0, 0.2, 1);
}
.ring-grade {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  font-weight: 900;
  letter-spacing: -0.02em;
}

.score-info { flex: 1; }
.score-value { font-size: 3rem; font-weight: 800; color: #0f172a; line-height: 1; }
.score-max { font-size: 1.2rem; color: #94a3b8; font-weight: 600; }
.score-sub { font-size: 0.9rem; color: #64748b; margin-top: 0.3rem; }
.score-label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.4rem; }
.score-pills { display: flex; flex-direction: column; gap: 0.5rem; align-items: flex-start; }
.status-pill { display: flex; align-items: center; gap: 0.4rem; padding: 0.4rem 0.8rem; border-radius: 20px; font-size: 0.82rem; font-weight: 600; }
.pill-ok { background: #064e3b; color: #34d399; border: 1px solid #059669; font-weight: 700; }
.pill-warn { background: #78350f; color: #fbbf24; border: 1px solid #d97706; font-weight: 700; }

/* Pulsing anomaly badge */
.pill-pulse {
  animation: pillPulse 2s ease-in-out infinite;
}
@keyframes pillPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(217, 119, 6, 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(217, 119, 6, 0); }
}

/* Hero detail link */
.hero-detail-link {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.76rem;
  font-weight: 700;
  color: #64748b;
  text-decoration: none;
  transition: color 0.2s;
}
.hero-detail-link:hover { color: #1e293b; }

/* Toolbar live-dot & auto-refresh badge */
.live-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #22c55e;
  flex-shrink: 0;
}
.live-dot.pulsing {
  background: #f59e0b;
  animation: dotBlink 0.8s ease-in-out infinite;
}
@keyframes dotBlink { 0%, 100% { opacity: 1; } 50% { opacity: 0.2; } }
.auto-refresh-badge {
  margin-left: auto;
  font-size: 0.68rem;
  font-weight: 600;
  color: #64748b;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  padding: 0.18rem 0.6rem;
  letter-spacing: 0.04em;
}

.loading-placeholder {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 2rem;
  color: #64748b;
  font-size: 0.95rem;
  background: rgba(0,0,0,0.03);
  border-radius: 12px;
}

/* Cards */
.card {
  background: rgba(255,255,255,0.85);
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0,0,0,0.05);
}
.card-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 1rem 1.5rem;
  background: rgba(248,250,252,0.9);
  border-bottom: 1px solid rgba(0,0,0,0.06);
  font-size: 0.95rem;
  font-weight: 600;
  color: #1e293b;
}
.card-header .btn { margin-left: auto; }

.icon-blue { color: #0284c7; }
.icon-amber { color: #d97706; }
.icon-purple { color: #9333ea; }

/* Metrics List */
.metrics-list {
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.metric-row {
  display: grid;
  grid-template-columns: 150px 1fr 55px 90px 28px;
  align-items: center;
  gap: 1rem;
}
.metric-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.88rem;
  color: #334155;
  font-weight: 600;
}
.metric-icon.status-ok { color: #16a34a; }
.metric-icon.status-warning { color: #d97706; }
.metric-icon.status-error { color: #dc2626; }
.bar-wrap {
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s ease-out; }
.bar-ok { background: linear-gradient(90deg, #16a34a, #4ade80); }
.bar-warning { background: linear-gradient(90deg, #d97706, #fbbf24); }
.bar-error { background: linear-gradient(90deg, #dc2626, #f87171); }
.metric-pct { font-weight: 800; font-size: 0.9rem; text-align: right; }
.pct-ok { color: #16a34a; }
.pct-warning { color: #d97706; }
.pct-error { color: #dc2626; }
.metric-count { font-size: 0.78rem; color: #64748b; text-align: right; font-variant-numeric: tabular-nums; }
.metric-badge { display: flex; align-items: center; justify-content: center; }
.badge-ok { color: #16a34a; }
.badge-warning { color: #d97706; }
.badge-error { color: #dc2626; }

/* Issues */
.issues-box {
  margin: 0 1.5rem 1.25rem;
  background: rgba(239,68,68,0.06);
  border: 1px solid rgba(239,68,68,0.2);
  border-radius: 10px;
  padding: 0.9rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.issue-line {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.84rem;
  color: #7f1d1d;
  line-height: 1.4;
  flex-wrap: wrap;
}
.issue-text { flex: 1; min-width: 0; }
.issue-icon { color: #d97706; flex-shrink: 0; margin-top: 0.1rem; }

/* Issue CTA button */
.issue-cta {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  white-space: nowrap;
  margin-left: auto;
  font-size: 0.75rem;
  font-weight: 700;
  color: #92400e;
  background: rgba(217,119,6,0.1);
  border: 1px solid rgba(217,119,6,0.3);
  border-radius: 6px;
  padding: 0.2rem 0.55rem;
  text-decoration: none;
  transition: all 0.2s;
  flex-shrink: 0;
}
.issue-cta:hover { background: rgba(217,119,6,0.2); color: #78350f; }
.all-ok {
  display: flex; align-items: center; gap: 0.5rem;
  margin: 0 1.5rem 1.25rem;
  background: rgba(16,163,74,0.06);
  border: 1px solid rgba(16,163,74,0.25);
  border-radius: 10px;
  padding: 0.9rem 1rem;
  font-size: 0.88rem;
  color: #166534;
  font-weight: 600;
}

/* Scoring */
.scoring-idle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1.25rem 1.5rem;
  font-size: 0.88rem;
  color: #64748b;
}
.scoring-running, .scoring-done, .scoring-error {
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.scoring-done, .scoring-error { flex-direction: row; align-items: center; gap: 1rem; }
.progress-header { display: flex; justify-content: space-between; font-size: 0.88rem; }
.progress-title { font-weight: 600; color: #1e293b; }
.progress-stats { color: #64748b; font-variant-numeric: tabular-nums; }
.progress-track { height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }
.progress-fill-blue { height: 100%; background: linear-gradient(90deg, #3b82f6, #60a5fa); border-radius: 4px; transition: width 0.4s ease; }
.scoring-detail { display: flex; align-items: center; gap: 1rem; font-size: 0.84rem; }
.text-ok { color: #4ade80; }
.text-err { color: #f87171; }
.pct-badge { margin-left: auto; font-weight: 800; color: #38bdf8; }

/* Scoring coverage (primary view) */
.scoring-coverage {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.cov-main { display: flex; flex-direction: column; gap: 0.35rem; }
.cov-numbers { display: flex; align-items: baseline; gap: 0.25rem; }
.cov-ok { font-size: 2.5rem; font-weight: 900; color: #0f172a; line-height: 1; }
.cov-sep { font-size: 1.5rem; color: #94a3b8; font-weight: 700; }
.cov-total { font-size: 1.5rem; font-weight: 700; color: #94a3b8; }
.cov-label { font-size: 0.9rem; color: #475569; font-weight: 500; }
.cov-avg { font-size: 0.82rem; color: #64748b; }
.cov-avg strong { color: #1e293b; }
.cov-gauge { display: flex; align-items: center; gap: 1rem; }
.cov-bar-track { flex: 1; height: 10px; background: #e2e8f0; border-radius: 5px; overflow: hidden; }
.cov-bar-fill { height: 100%; border-radius: 5px; transition: width 0.7s ease-out; }
.cov-bar-ok { background: linear-gradient(90deg, #16a34a, #4ade80); }
.cov-bar-warning { background: linear-gradient(90deg, #d97706, #fbbf24); }
.cov-bar-error { background: linear-gradient(90deg, #dc2626, #f87171); }
.cov-pct { font-size: 1.1rem; font-weight: 800; min-width: 52px; text-align: right; }
.cov-pct-ok { color: #16a34a; }
.cov-pct-warning { color: #d97706; }
.cov-pct-error { color: #dc2626; }
.cov-action {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.7rem 0.9rem;
  border-radius: 8px;
  background: rgba(234,88,12,0.08);
  border: 1px solid rgba(234,88,12,0.25);
  color: #9a3412;
  font-size: 0.85rem;
}
.cov-action strong { color: #7c2d12; }
.cov-action-ok { background: rgba(16,163,74,0.08); border-color: rgba(16,163,74,0.25); color: #166534; }

/* Last run (secondary) */
.scoring-run-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.5rem;
  border-top: 1px solid rgba(0,0,0,0.06);
  background: rgba(248,250,252,0.8);
  gap: 1rem;
}
.run-info { display: flex; align-items: center; gap: 0.5rem; }
.run-link {
  display: inline-flex; align-items: center; gap: 0.3rem;
  font-size: 0.75rem; font-weight: 700;
  color: #d97706; text-decoration: none; transition: opacity 0.2s;
}
.run-link:hover { opacity: 0.75; }
.run-badge {
  display: flex; align-items: center; gap: 0.35rem;
  font-size: 0.82rem; font-weight: 600;
  padding: 0.25rem 0.75rem; border-radius: 20px;
}
.run-idle { background: rgba(100,116,139,0.1); color: #475569; }
.run-running { background: rgba(37,99,235,0.1); color: #1d4ed8; }
.run-uploading { background: rgba(217,119,6,0.1); color: #92400e; }
.run-batch_running { background: rgba(124,58,237,0.12); color: #5b21b6; }
.run-applying { background: rgba(6,182,212,0.1); color: #155e75; }
.run-completed { background: rgba(16,163,74,0.1); color: #166534; }
.run-error { background: rgba(220,38,38,0.1); color: #991b1b; }

/* Batch job ID */
.run-job-id {
  display: flex; align-items: center; gap: 0.4rem;
  margin-top: 0.5rem; font-size: 0.78rem; color: #64748b;
}
.run-job-label { font-weight: 600; }
.run-job-code {
  background: #f1f5f9; border: 1px solid #e2e8f0;
  border-radius: 4px; padding: 0.1rem 0.4rem;
  font-family: monospace; font-size: 0.75rem; color: #475569;
  max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* Erreur inline */
.run-error-msg {
  display: flex; align-items: flex-start; gap: 0.4rem;
  margin-top: 0.5rem; font-size: 0.79rem;
  color: #991b1b; background: rgba(220,38,38,0.06);
  border-radius: 6px; padding: 0.4rem 0.6rem;
}

/* Logs pipeline */
.run-logs { margin-top: 0.75rem; }
.run-logs-label {
  font-size: 0.72rem; color: #94a3b8;
  text-transform: uppercase; letter-spacing: 0.06em;
  font-weight: 700; margin-bottom: 0.35rem;
}
.run-log-line {
  display: flex; align-items: flex-start; gap: 0.5rem;
  font-size: 0.79rem; color: #64748b;
  padding: 0.2rem 0; border-left: none;
  transition: color 0.3s;
}
.run-log-line.run-log-active { color: #1e293b; font-weight: 600; }
.run-log-dot {
  flex-shrink: 0; width: 7px; height: 7px;
  border-radius: 50%; margin-top: 4px;
}
.dot-active { background: #22c55e; animation: dotBlink 1.2s ease-in-out infinite; }
.dot-done { background: #cbd5e1; }

.scoring-done { background: rgba(16,185,129,0.05); }
.icon-ok { color: #4ade80; flex-shrink: 0; }
.done-title { font-weight: 700; color: #f8fafc; font-size: 0.95rem; }
.done-sub { font-size: 0.82rem; color: #94a3b8; margin-top: 0.2rem; }
.done-rate { margin-left: auto; font-size: 1.1rem; font-weight: 800; color: #4ade80; }

.scoring-error { background: rgba(239,68,68,0.05); color: #fca5a5; font-size: 0.88rem; }



/* Pipeline Grid */
.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1px;
  background: rgba(0,0,0,0.06);
}
@media (min-width: 700px) {
  .pipeline-grid { grid-template-columns: repeat(4, 1fr); }
}
.pipeline-card {
  background: rgba(255,255,255,0.03);
  padding: 1.5rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  text-decoration: none;
}
.pipeline-card-link {
  cursor: pointer;
  transition: background 0.2s;
}
.pipeline-card-link:hover {
  background: rgba(0,0,0,0.03);
}
.pc-icon { margin-bottom: 0.25rem; transition: color 0.3s; }
.pc-icon-grade-a { color: #4ade80; }
.pc-icon-grade-b { color: #60a5fa; }
.pc-icon-grade-c { color: #fbbf24; }
.pc-icon-grade-d { color: #f87171; }
.pc-icon:not([class*='pc-icon-grade']) { color: #64748b; }
.pc-label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
.pc-value { font-size: 1.4rem; font-weight: 800; color: #0f172a; }
.pc-sub { font-size: 0.78rem; color: #64748b; }

/* Progress bar inside pipeline card */
.pc-bar {
  height: 4px;
  background: #e2e8f0;
  border-radius: 2px;
  overflow: hidden;
  margin: 0.3rem 0;
}
.pc-bar-fill { height: 100%; border-radius: 2px; transition: width 0.8s ease-out; }
.grade-bar-a { background: linear-gradient(90deg, #16a34a, #4ade80); }
.grade-bar-b { background: linear-gradient(90deg, #2563eb, #60a5fa); }
.grade-bar-c { background: linear-gradient(90deg, #d97706, #fbbf24); }
.grade-bar-d { background: linear-gradient(90deg, #dc2626, #f87171); }

.pc-status {
  margin-top: 0.35rem;
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 20px;
  font-size: 0.72rem;
  font-weight: 700;
  width: fit-content;
}
.grade-a { background: #052e16; color: #4ade80; border: 1px solid #16a34a; }
.grade-b { background: #0c1a4f; color: #60a5fa; border: 1px solid #2563eb; }
.grade-c { background: #431407; color: #fbbf24; border: 1px solid #d97706; }
.grade-d { background: #450a0a; color: #f87171; border: 1px solid #dc2626; }

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.55rem 1.1rem;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-refresh {
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}
.btn-refresh:hover:not(:disabled) { background: #e2e8f0; color: #334155; }
.btn-resume {
  background: linear-gradient(135deg, #7c3aed, #4f46e5);
  color: #fff;
  border: none;
  font-size: 0.78rem;
  padding: 0.3rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  transition: opacity 0.15s;
}
.btn-resume:hover { opacity: 0.85; }
.run-resume-wrap {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-top: 0.6rem;
  padding-top: 0.6rem;
  border-top: 1px dashed rgba(99, 102, 241, 0.25);
}
.run-resume-hint {
  font-size: 0.72rem;
  color: #94a3b8;
  font-style: italic;
}
.btn-sm { padding: 0.3rem 0.6rem; font-size: 0.78rem; }

.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* Drive Ingestion section */
.icon-violet { color: #a78bfa; }
.header-link {
  margin-left: auto;
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 0.78rem; font-weight: 700; color: #a78bfa;
  text-decoration: none; transition: opacity 0.2s;
}
.header-link:hover { opacity: 0.75; }

.drive-hero {
  display: flex; align-items: center; gap: 1.5rem;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  flex-wrap: wrap;
}
.drive-grade {
  width: 56px; height: 56px; border-radius: 50%; border: 3px solid;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.6rem; font-weight: 900; flex-shrink: 0;
}
.drive-volumes {
  display: flex; gap: 1.25rem; flex-wrap: wrap; flex: 1;
}
.dv-item {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 8px 12px; background: rgba(255,255,255,0.8);
  border-radius: 10px; border: 1px solid rgba(0,0,0,0.08);
  min-width: 64px;
}
.dv-n { font-size: 1.2rem; font-weight: 800; color: #0f172a; line-height: 1; }
.dv-l { font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; }
.dv-ok .dv-n { color: #16a34a; }
.dv-err .dv-n { color: #dc2626; }
.drive-score {
  font-size: 2rem; font-weight: 900; color: #0f172a; white-space: nowrap;
}
.drive-score-max { font-size: 1rem; color: #475569; font-weight: 600; }
.drive-metric-row {
  grid-template-columns: 180px 1fr 65px 90px 28px;
}
.text-ok { color: #4ade80; }
.text-warn { color: #fbbf24; }
.text-err { color: #f87171; }

/* Scoring section labels (sub-sections) */
.scoring-section-label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 1.5rem;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #64748b;
  background: rgba(0,0,0,0.04);
}

/* SVG ring track */
.score-ring-track { stroke: #e2e8f0; }
</style>
