<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import axios from 'axios'
import {
  Activity, CheckCircle2, AlertTriangle, XCircle,
  Clock, FileText, Radio, Loader2, RefreshCw, Zap,
  ArrowRight, FolderOpen
} from 'lucide-vue-next'

// ─── Types ────────────────────────────────────────────────────────────────────
interface PipelineStatus {
  pending: number
  queued: number
  processing: number
  imported: number
  ignored: number
  errors: number
}

// ─── State ────────────────────────────────────────────────────────────────────
const pipelineStatus = ref<PipelineStatus | null>(null)
const pollingInterval = ref<ReturnType<typeof setInterval> | null>(null)
const lastRefresh = ref<Date | null>(null)
const isLoading = ref(false)

// ─── Computed ─────────────────────────────────────────────────────────────────
const totalFiles = computed(() => {
  if (!pipelineStatus.value) return 0
  const s = pipelineStatus.value
  return s.pending + s.queued + s.processing + s.imported + s.ignored + s.errors
})

const processedFiles = computed(() => {
  if (!pipelineStatus.value) return 0
  return pipelineStatus.value.imported + pipelineStatus.value.ignored + pipelineStatus.value.errors
})

const progressPct = computed(() => {
  if (!totalFiles.value) return 0
  return Math.round((processedFiles.value / totalFiles.value) * 100)
})

const isActive = computed(() => {
  if (!pipelineStatus.value) return false
  return pipelineStatus.value.processing > 0 || pipelineStatus.value.queued > 0 || pipelineStatus.value.pending > 0
})

const pipelineStatusLabel = computed(() => {
  if (!pipelineStatus.value) return 'Chargement...'
  const s = pipelineStatus.value
  if (s.processing > 0) return 'Analyse IA en cours'
  if (s.queued > 0) return 'En file Pub/Sub'
  if (s.pending > 0) return 'En attente'
  if (s.errors > 0 && s.pending === 0 && s.queued === 0) return 'Erreurs détectées'
  if (totalFiles.value === 0) return 'Aucun fichier'
  return 'Pipeline stable'
})

const pipelineStatusClass = computed(() => {
  if (!pipelineStatus.value) return 'pill-idle'
  const s = pipelineStatus.value
  if (s.processing > 0) return 'pill-running'
  if (s.queued > 0) return 'pill-queued'
  if (s.errors > 0 && s.pending === 0 && s.queued === 0) return 'pill-error'
  return 'pill-stable'
})

// ─── Data fetching ────────────────────────────────────────────────────────────
const fetchStatus = async () => {
  if (isLoading.value) return
  isLoading.value = true
  try {
    const resp = await axios.get('/api/drive/status')
    pipelineStatus.value = resp.data
    lastRefresh.value = new Date()

    // Poll faster if active
    if (isActive.value) {
      if (!pollingInterval.value) startPolling(4000)
    } else {
      stopPolling()
      startPolling(15000) // Slower refresh when idle
    }
  } catch (e) {
    console.error('[CVImportMonitor] Failed to fetch pipeline status', e)
  } finally {
    isLoading.value = false
  }
}

const startPolling = (interval = 4000) => {
  stopPolling()
  pollingInterval.value = setInterval(fetchStatus, interval)
}

const stopPolling = () => {
  if (pollingInterval.value) {
    clearInterval(pollingInterval.value)
    pollingInterval.value = null
  }
}

onMounted(fetchStatus)
onUnmounted(stopPolling)

const formatTime = (date: Date | null) => {
  if (!date) return '—'
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<template>
  <div class="monitor-card">
    <!-- Header -->
    <div class="monitor-header">
      <div class="header-left">
        <div class="header-icon" :class="isActive ? 'icon-active' : 'icon-idle'">
          <Activity size="20" />
        </div>
        <div>
          <h3>Pipeline d'Import Drive</h3>
          <span class="header-sub">Statut temps réel des CVs en cours d'ingestion IA</span>
        </div>
      </div>
      <div class="header-right">
        <div class="status-pill" :class="pipelineStatusClass">
          <span class="status-dot" :class="isActive ? 'dot-pulse' : ''"></span>
          {{ pipelineStatusLabel }}
        </div>
        <button
          class="refresh-btn"
          @click="fetchStatus"
          :title="lastRefresh ? `Rafraîchi à ${formatTime(lastRefresh)}` : 'Rafraîchir'"
          aria-label="Rafraîchir le statut du pipeline"
          :class="{ 'spinning': isLoading }"
        >
          <RefreshCw size="14" />
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!pipelineStatus" class="idle-state">
      <Loader2 size="28" class="idle-spinner" />
      <p>Chargement du statut du pipeline…</p>
    </div>

    <div v-else class="monitor-body">
      <!-- KPI Row -->
      <div class="kpi-row">
        <div class="kpi-card kpi-pending" :class="{ 'kpi-active': pipelineStatus.pending > 0 }">
          <div class="kpi-icon"><Clock size="16" /></div>
          <div class="kpi-value">{{ pipelineStatus.pending }}</div>
          <div class="kpi-label">En attente</div>
        </div>
        <div class="kpi-card kpi-queued" :class="{ 'kpi-active': pipelineStatus.queued > 0 }">
          <div class="kpi-icon"><Radio size="16" /></div>
          <div class="kpi-value">{{ pipelineStatus.queued }}</div>
          <div class="kpi-label">File Pub/Sub</div>
        </div>
        <div class="kpi-card kpi-processing" :class="{ 'kpi-active': pipelineStatus.processing > 0 }">
          <div class="kpi-icon"><Loader2 size="16" :class="{ 'spin-icon': pipelineStatus.processing > 0 }" /></div>
          <div class="kpi-value">{{ pipelineStatus.processing }}</div>
          <div class="kpi-label">Analyse IA</div>
        </div>
        <div class="kpi-card kpi-success">
          <div class="kpi-icon"><CheckCircle2 size="16" /></div>
          <div class="kpi-value">{{ pipelineStatus.imported }}</div>
          <div class="kpi-label">Importés</div>
        </div>
        <div class="kpi-card kpi-ignored">
          <div class="kpi-icon"><FileText size="16" /></div>
          <div class="kpi-value">{{ pipelineStatus.ignored }}</div>
          <div class="kpi-label">Ignorés</div>
        </div>
        <div class="kpi-card" :class="pipelineStatus.errors > 0 ? 'kpi-error' : 'kpi-ignored'">
          <div class="kpi-icon"><XCircle size="16" /></div>
          <div class="kpi-value">{{ pipelineStatus.errors }}</div>
          <div class="kpi-label">Erreurs</div>
        </div>
      </div>

      <!-- Progress bar (only if there are files) -->
      <div v-if="totalFiles > 0" class="progress-section">
        <div class="progress-meta">
          <span>{{ processedFiles }} / {{ totalFiles }} fichiers traités</span>
          <span class="progress-pct">{{ progressPct }}%</span>
        </div>
        <div class="progress-track">
          <!-- Imported (green) -->
          <div
            class="progress-fill fill-imported"
            :style="{ width: `${Math.round(pipelineStatus.imported / totalFiles * 100)}%` }"
          ></div>
          <!-- Ignored (gray) -->
          <div
            class="progress-fill fill-ignored"
            :style="{ width: `${Math.round(pipelineStatus.ignored / totalFiles * 100)}%` }"
          ></div>
          <!-- Errors (red) -->
          <div
            class="progress-fill fill-error"
            :style="{ width: `${Math.round(pipelineStatus.errors / totalFiles * 100)}%` }"
          ></div>
        </div>
        <div class="progress-legend">
          <span class="legend-item"><span class="dot dot-green"></span>Importés</span>
          <span class="legend-item"><span class="dot dot-gray"></span>Ignorés (non-CV)</span>
          <span class="legend-item"><span class="dot dot-red"></span>Erreurs</span>
        </div>
      </div>

      <!-- Alert banners -->
      <div v-if="pipelineStatus.queued > 0" class="alert-banner alert-info">
        <Radio size="14" />
        <span>
          <strong>{{ pipelineStatus.queued }} CV(s)</strong> en file Pub/Sub — en attente de traitement par l'IA Gemini.
        </span>
      </div>
      <div v-if="pipelineStatus.errors > 0" class="alert-banner alert-error">
        <AlertTriangle size="14" />
        <span>
          <strong>{{ pipelineStatus.errors }} fichier(s)</strong> en erreur — consultez la section Drive ci-dessous pour les détails et relancer.
        </span>
      </div>
      <div v-if="!isActive && pipelineStatus.errors === 0 && totalFiles > 0" class="alert-banner alert-success">
        <CheckCircle2 size="14" />
        <span>Pipeline stable — tous les fichiers disponibles ont été traités.</span>
      </div>
      <div v-if="totalFiles === 0" class="alert-banner alert-neutral">
        <FolderOpen size="14" />
        <span>Aucun fichier dans le pipeline. Configurez un dossier Drive source pour démarrer l'import.</span>
      </div>

      <!-- Quick action -->
      <div class="quick-access">
        <RouterLink to="/admin/reanalysis" class="quick-link">
          <Zap size="13" />
          Réanalyse batch des profils
          <ArrowRight size="13" />
        </RouterLink>
        <span class="quick-sep">·</span>
        <span class="last-refresh">Mis à jour {{ formatTime(lastRefresh) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.monitor-card {
  background: rgba(255,255,255,0.75);
  backdrop-filter: blur(20px);
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.6);
  box-shadow: 0 8px 32px rgba(0,0,0,0.06);
  overflow: hidden;
}

/* ── Header ── */
.monitor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  background: rgba(255,255,255,0.5);
}
.header-left { display: flex; align-items: center; gap: 12px; }
.header-icon {
  padding: 10px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.icon-active { background: rgba(227,25,55,0.12); color: #E31937; }
.icon-idle   { background: #f1f5f9; color: #64748b; }

.monitor-header h3 { font-size: 1rem; font-weight: 700; color: #1e293b; margin: 0; }
.header-sub { font-size: 0.75rem; color: #94a3b8; }
.header-right { display: flex; align-items: center; gap: 10px; }

/* ── Status pills ── */
.status-pill {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 30px;
  font-size: 0.75rem; font-weight: 700;
}
.pill-idle    { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
.pill-running { background: rgba(227,25,55,0.1); color: #E31937; border: 1px solid rgba(227,25,55,0.3); }
.pill-queued  { background: rgba(139,92,246,0.1); color: #7c3aed; border: 1px solid rgba(139,92,246,0.3); }
.pill-error   { background: rgba(220,38,38,0.1); color: #dc2626; border: 1px solid rgba(220,38,38,0.3); }
.pill-stable  { background: rgba(16,163,74,0.1); color: #16a34a; border: 1px solid rgba(16,163,74,0.3); }

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
.refresh-btn.spinning svg { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Idle/loading state ── */
.idle-state {
  padding: 2.5rem; text-align: center; color: #94a3b8;
  display: flex; flex-direction: column; align-items: center; gap: 12px;
}
.idle-spinner { animation: spin 1.5s linear infinite; opacity: 0.4; }
.idle-state p { font-size: 0.9rem; margin: 0; }

/* ── Body ── */
.monitor-body { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: 1rem; }

/* ── KPI Row ── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8px;
}

@media (max-width: 768px) {
  .kpi-row { grid-template-columns: repeat(3, 1fr); }
}

.kpi-card {
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 12px 8px; text-align: center; transition: all 0.3s;
  display: flex; flex-direction: column; align-items: center; gap: 4px;
}
.kpi-active { transform: scale(1.03); }

.kpi-pending  { border-top: 3px solid #f59e0b; }
.kpi-queued   { border-top: 3px solid #8b5cf6; }
.kpi-processing { border-top: 3px solid #3b82f6; }
.kpi-success  { border-top: 3px solid #16a34a; background: #f0fdf4; border-color: #bbf7d0; }
.kpi-ignored  { border-top: 3px solid #94a3b8; }
.kpi-error    { border-top: 3px solid #dc2626; background: #fff1f2; border-color: #fecdd3; }

.kpi-pending.kpi-active  { background: #fffbeb; border-color: #fde68a; box-shadow: 0 4px 12px rgba(245,158,11,0.15); }
.kpi-queued.kpi-active   { background: rgba(139,92,246,0.06); border-color: rgba(139,92,246,0.3); box-shadow: 0 4px 12px rgba(139,92,246,0.15); }
.kpi-processing.kpi-active { background: rgba(59,130,246,0.06); border-color: rgba(59,130,246,0.3); box-shadow: 0 4px 12px rgba(59,130,246,0.15); }

.kpi-icon { opacity: 0.5; display: flex; }
.kpi-pending .kpi-icon   { color: #f59e0b; }
.kpi-queued .kpi-icon    { color: #8b5cf6; }
.kpi-processing .kpi-icon { color: #3b82f6; }
.kpi-success .kpi-icon   { color: #16a34a; opacity: 0.8; }
.kpi-ignored .kpi-icon   { color: #64748b; }
.kpi-error .kpi-icon     { color: #dc2626; opacity: 0.8; }

.kpi-value { font-size: 1.5rem; font-weight: 800; color: #1e293b; line-height: 1; }
.kpi-success .kpi-value  { color: #16a34a; }
.kpi-error .kpi-value    { color: #dc2626; }

.kpi-label { font-size: 0.65rem; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }

.spin-icon { animation: spin 1.5s linear infinite; }

/* ── Progress ── */
.progress-section { background: #f8fafc; border-radius: 12px; padding: 14px 16px; border: 1px solid #e2e8f0; }
.progress-meta { display: flex; justify-content: space-between; font-size: 0.75rem; color: #64748b; margin-bottom: 8px; }
.progress-pct { font-weight: 700; color: #1e293b; }
.progress-track {
  height: 8px; background: #e2e8f0; border-radius: 999px; overflow: hidden;
  display: flex;
}
.progress-fill { height: 100%; transition: width 0.6s ease; }
.fill-imported { background: #16a34a; }
.fill-ignored  { background: #94a3b8; }
.fill-error    { background: #dc2626; }

.progress-legend { display: flex; gap: 12px; margin-top: 8px; }
.legend-item { display: flex; align-items: center; gap: 4px; font-size: 0.7rem; color: #64748b; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-green { background: #16a34a; }
.dot-gray  { background: #94a3b8; }
.dot-red   { background: #dc2626; }

/* ── Alert banners ── */
.alert-banner {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 14px; border-radius: 10px;
  font-size: 0.82rem; line-height: 1.5;
}
.alert-info    { background: rgba(139,92,246,0.08); color: #7c3aed; border: 1px solid rgba(139,92,246,0.2); }
.alert-error   { background: rgba(220,38,38,0.07); color: #b91c1c; border: 1px solid rgba(220,38,38,0.2); }
.alert-success { background: rgba(16,163,74,0.07); color: #166534; border: 1px solid rgba(16,163,74,0.2); }
.alert-neutral { background: #f8fafc; color: #475569; border: 1px solid #e2e8f0; }
.alert-banner svg { flex-shrink: 0; margin-top: 2px; }

/* ── Quick access ── */
.quick-access {
  display: flex; align-items: center; gap: 10px;
  padding-top: 4px; font-size: 0.75rem; color: #94a3b8;
}
.quick-link {
  display: inline-flex; align-items: center; gap: 5px;
  color: #E31937; text-decoration: none; font-weight: 600;
  transition: opacity 0.2s;
}
.quick-link:hover { opacity: 0.75; }
.quick-sep { color: #e2e8f0; }
.last-refresh { margin-left: auto; }
</style>
