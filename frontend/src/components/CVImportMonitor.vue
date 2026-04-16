<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import axios from 'axios'
import {
  Activity, CheckCircle2, AlertTriangle, XCircle,
  RefreshCw, Clock, FileText, TrendingUp, ChevronDown, ChevronUp
} from 'lucide-vue-next'
import { authService } from '../services/auth'

// ─── Types ────────────────────────────────────────────────────────────────────
interface ReanalysisStatus {
  status: 'idle' | 'running' | 'completed'
  total_cvs?: number
  processed_count?: number
  error_count?: number
  mismatch_count?: number
  errors?: string[]
  logs?: string[]
  start_time?: string
  end_time?: string
  updated_at?: string
  message?: string
}

// ─── State ────────────────────────────────────────────────────────────────────
const reanalysisStatus = ref<ReanalysisStatus | null>(null)
const pollingInterval = ref<ReturnType<typeof setInterval> | null>(null)
const isLogsExpanded = ref(false)
const isErrorsExpanded = ref(false)
const lastRefresh = ref<Date | null>(null)

// ─── Computed ─────────────────────────────────────────────────────────────────
const progressPct = computed(() => {
  if (!reanalysisStatus.value) return 0
  const { total_cvs, processed_count, error_count } = reanalysisStatus.value
  if (!total_cvs || total_cvs === 0) return 0
  return Math.round(((processed_count ?? 0) + (error_count ?? 0)) / total_cvs * 100)
})

const statusColor = computed(() => {
  const s = reanalysisStatus.value?.status
  if (s === 'running') return '#E31937'
  if (s === 'completed') return '#16a34a'
  return '#94a3b8'
})

const statusLabel = computed(() => {
  const s = reanalysisStatus.value?.status
  if (s === 'running') return 'En cours'
  if (s === 'completed') return 'Terminée'
  return 'Aucune tâche'
})

const hasErrors = computed(() =>
  (reanalysisStatus.value?.error_count ?? 0) > 0 ||
  (reanalysisStatus.value?.errors?.length ?? 0) > 0
)

const recentLogs = computed(() =>
  (reanalysisStatus.value?.logs ?? []).slice(-10).reverse()
)

const elapsedTime = computed(() => {
  if (!reanalysisStatus.value?.start_time) return null
  const start = new Date(reanalysisStatus.value.start_time)
  const end = reanalysisStatus.value.end_time
    ? new Date(reanalysisStatus.value.end_time)
    : new Date()
  const diffMs = end.getTime() - start.getTime()
  const mins = Math.floor(diffMs / 60000)
  const secs = Math.floor((diffMs % 60000) / 1000)
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
})

// ─── Data fetching ────────────────────────────────────────────────────────────
const fetchStatus = async () => {
  try {
    const resp = await axios.get('/api/cv/reanalyze/status', {
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    reanalysisStatus.value = resp.data
    lastRefresh.value = new Date()

    if (resp.data.status === 'running') {
      startPolling()
    } else {
      stopPolling()
    }
  } catch (e) {
    console.error('[CVImportMonitor] Failed to fetch reanalysis status', e)
  }
}

const startPolling = () => {
  if (pollingInterval.value) return
  pollingInterval.value = setInterval(fetchStatus, 4000)
}

const stopPolling = () => {
  if (pollingInterval.value) {
    clearInterval(pollingInterval.value)
    pollingInterval.value = null
  }
}

onMounted(fetchStatus)
onUnmounted(stopPolling)

const formatTime = (iso?: string) => {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

const logClass = (log: string) => {
  if (log.includes('ERREUR') || log.includes('ÉCHEC') || log.includes('ERROR')) return 'log-error'
  if (log.includes('⚠️') || log.includes('WARN') || log.includes('ALERTE')) return 'log-warn'
  if (log.includes('TERMINÉ') || log.includes('Finished') || log.includes('SUCCESS')) return 'log-success'
  return ''
}
</script>

<template>
  <div class="monitor-card">
    <!-- Header -->
    <div class="monitor-header">
      <div class="header-left">
        <div class="header-icon" :style="{ background: `${statusColor}22`, color: statusColor }">
          <Activity size="20" />
        </div>
        <div>
          <h3>Moniteur des Analyses CV</h3>
          <span class="header-sub">Réanalyse batch & ingestion IA</span>
        </div>
      </div>
      <div class="header-right">
        <div class="status-pill" :class="`pill-${reanalysisStatus?.status ?? 'idle'}`">
          <span class="status-dot" :class="reanalysisStatus?.status === 'running' ? 'dot-pulse' : ''"></span>
          {{ statusLabel }}
        </div>
        <button class="refresh-btn" @click="fetchStatus" :title="lastRefresh ? `Rafraîchi à ${formatTime(lastRefresh?.toISOString())}` : ''" aria-label="Rafraîchir le statut">
          <RefreshCw size="14" />
        </button>
      </div>
    </div>

    <!-- Idle state -->
    <div v-if="!reanalysisStatus || reanalysisStatus.status === 'idle'" class="idle-state">
      <FileText size="32" class="idle-icon" />
      <p>Aucune réanalyse en cours.<br>
        <RouterLink to="/admin/reanalysis" class="start-link">Lancer une réanalyse →</RouterLink>
      </p>
    </div>

    <!-- Active / Completed state -->
    <div v-else class="monitor-body">
      <!-- KPI Row -->
      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-value">{{ reanalysisStatus.total_cvs ?? 0 }}</div>
          <div class="kpi-label">CVs total</div>
        </div>
        <div class="kpi-card kpi-success">
          <div class="kpi-value">{{ reanalysisStatus.processed_count ?? 0 }}</div>
          <div class="kpi-label">Traités</div>
        </div>
        <div class="kpi-card" :class="hasErrors ? 'kpi-error' : ''">
          <div class="kpi-value">{{ reanalysisStatus.error_count ?? 0 }}</div>
          <div class="kpi-label">Erreurs</div>
        </div>
        <div class="kpi-card kpi-warn">
          <div class="kpi-value">{{ reanalysisStatus.mismatch_count ?? 0 }}</div>
          <div class="kpi-label">Alertes ID</div>
        </div>
      </div>

      <!-- Progress Bar -->
      <div class="progress-section">
        <div class="progress-meta">
          <span>Progression</span>
          <span class="progress-pct">{{ progressPct }}%</span>
        </div>
        <div class="progress-track">
          <div
            class="progress-fill"
            :style="{ width: `${progressPct}%`, background: hasErrors ? 'linear-gradient(90deg, #16a34a, #E31937)' : '#16a34a' }"
            :class="reanalysisStatus.status === 'running' ? 'progress-animated' : ''"
          ></div>
        </div>
        <div class="progress-meta" style="margin-top: 6px;">
          <span v-if="reanalysisStatus.start_time">
            <Clock size="12" style="display:inline; vertical-align: middle;" />
            Démarré {{ formatTime(reanalysisStatus.start_time) }}
          </span>
          <span v-if="elapsedTime" class="elapsed">
            <TrendingUp size="12" style="display:inline; vertical-align: middle;" />
            {{ elapsedTime }}
          </span>
        </div>
      </div>

      <!-- Errors section -->
      <div v-if="hasErrors" class="errors-section">
        <button class="expand-btn error-expand" @click="isErrorsExpanded = !isErrorsExpanded" aria-label="Afficher les erreurs">
          <XCircle size="14" />
          <span>{{ reanalysisStatus.errors?.length ?? reanalysisStatus.error_count }} erreur(s)</span>
          <component :is="isErrorsExpanded ? ChevronUp : ChevronDown" size="14" />
        </button>
        <div v-if="isErrorsExpanded" class="errors-list">
          <div v-for="(err, i) in reanalysisStatus.errors" :key="i" class="error-item">
            {{ err }}
          </div>
          <div v-if="!reanalysisStatus.errors?.length" class="error-item">
            {{ reanalysisStatus.error_count }} CV(s) en erreur (détails indisponibles)
          </div>
        </div>
      </div>

      <!-- Completed status -->
      <div v-if="reanalysisStatus.status === 'completed'" class="completed-banner">
        <CheckCircle2 size="16" />
        <span>Réanalyse terminée — {{ reanalysisStatus.processed_count }} CV(s) traités avec succès</span>
      </div>

      <!-- Logs section -->
      <div class="logs-section">
        <button class="expand-btn" @click="isLogsExpanded = !isLogsExpanded" aria-label="Afficher les logs">
          <Activity size="14" />
          <span>Journal d'exécution ({{ recentLogs.length }} récents)</span>
          <component :is="isLogsExpanded ? ChevronUp : ChevronDown" size="14" />
        </button>
        <div v-if="isLogsExpanded" class="logs-console">
          <div v-if="recentLogs.length === 0" class="log-empty">Aucun log disponible.</div>
          <div v-for="(log, i) in recentLogs" :key="i" class="log-entry" :class="logClass(log)">
            {{ log }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.monitor-card {
  background: rgba(255,255,255,0.7);
  backdrop-filter: blur(20px);
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.5);
  box-shadow: 0 8px 32px rgba(0,0,0,0.05);
  overflow: hidden;
}

.monitor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  background: rgba(255,255,255,0.6);
}
.header-left { display: flex; align-items: center; gap: 12px; }
.header-icon {
  padding: 10px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.monitor-header h3 { font-size: 1rem; font-weight: 700; color: #1e293b; margin: 0; }
.header-sub { font-size: 0.75rem; color: #94a3b8; }
.header-right { display: flex; align-items: center; gap: 10px; }

/* Status pills */
.status-pill {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 30px;
  font-size: 0.75rem; font-weight: 700;
}
.pill-idle      { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
.pill-running   { background: rgba(227,25,55,0.1); color: #E31937; border: 1px solid rgba(227,25,55,0.3); }
.pill-completed { background: rgba(22,163,74,0.1); color: #16a34a; border: 1px solid rgba(22,163,74,0.3); }

.status-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; display: inline-block;
}
.dot-pulse { animation: dot-pulse 1.2s ease-in-out infinite; }
@keyframes dot-pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.6); } }

.refresh-btn {
  background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 6px 8px; cursor: pointer; color: #64748b;
  display: flex; align-items: center; transition: all 0.2s;
}
.refresh-btn:hover { background: #e2e8f0; color: #1e293b; }

/* Idle */
.idle-state { padding: 2.5rem; text-align: center; color: #94a3b8; }
.idle-icon { margin: 0 auto 12px; opacity: 0.3; }
.idle-state p { font-size: 0.9rem; line-height: 1.6; }
.start-link { color: #E31937; text-decoration: none; font-weight: 600; }
.start-link:hover { text-decoration: underline; }

/* Body */
.monitor-body { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: 1rem; }

/* KPI Row */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.kpi-card {
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 12px; text-align: center;
}
.kpi-success { border-color: #bbf7d0; background: #f0fdf4; }
.kpi-error   { border-color: #fca5a5; background: #fff1f1; }
.kpi-warn    { border-color: #fde68a; background: #fffbeb; }
.kpi-value { font-size: 1.5rem; font-weight: 800; color: #1e293b; }
.kpi-success .kpi-value { color: #16a34a; }
.kpi-error .kpi-value   { color: #dc2626; }
.kpi-warn .kpi-value    { color: #d97706; }
.kpi-label { font-size: 0.7rem; color: #64748b; font-weight: 600; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.05em; }

/* Progress */
.progress-section { background: #f8fafc; border-radius: 12px; padding: 14px 16px; border: 1px solid #e2e8f0; }
.progress-meta { display: flex; justify-content: space-between; font-size: 0.75rem; color: #64748b; margin-bottom: 8px; }
.progress-pct { font-weight: 700; color: #1e293b; }
.elapsed { color: #64748b; }
.progress-track { height: 8px; background: #e2e8f0; border-radius: 999px; overflow: hidden; }
.progress-fill { height: 100%; border-radius: 999px; transition: width 0.6s ease; }
.progress-animated { animation: progress-shimmer 2s linear infinite; background-size: 200% 100% !important; }
@keyframes progress-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}

/* Errors */
.errors-section { border-radius: 10px; overflow: hidden; }
.errors-list { background: #fff1f2; padding: 10px 12px; }
.error-item { font-size: 0.75rem; color: #b91c1c; padding: 4px 0; border-bottom: 1px solid #fecdd3; line-height: 1.4; }
.error-item:last-child { border-bottom: none; }

/* Completed */
.completed-banner {
  background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px;
  padding: 10px 14px; display: flex; align-items: center; gap: 8px;
  font-size: 0.8rem; font-weight: 600; color: #166534;
}

/* Logs */
.logs-section { border-radius: 10px; overflow: hidden; border: 1px solid #e2e8f0; }
.expand-btn {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 10px 14px; background: #f8fafc;
  border: none; cursor: pointer; font-size: 0.8rem; font-weight: 600; color: #475569;
  transition: background 0.2s;
}
.expand-btn:hover { background: #f1f5f9; }
.error-expand { color: #dc2626; background: #fff1f2; }
.error-expand:hover { background: #ffe4e6; }
.logs-console {
  background: #0f172a; padding: 10px 14px; max-height: 200px; overflow-y: auto;
  font-family: 'Fira Code', 'Monaco', monospace; font-size: 0.72rem;
}
.log-empty { color: #475569; font-style: italic; }
.log-entry { padding: 3px 0; color: #38bdf8; border-bottom: 1px solid rgba(255,255,255,0.04); line-height: 1.4; }
.log-error  { color: #f87171; }
.log-warn   { color: #fbbf24; }
.log-success { color: #34d399; }
</style>
