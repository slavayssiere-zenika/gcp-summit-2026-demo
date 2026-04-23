<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import axios from 'axios'
import {
  Activity, CheckCircle2, AlertTriangle, XCircle,
  Clock, FileText, Radio, Loader2, RefreshCw, Zap,
  ArrowRight, FolderOpen, User
} from 'lucide-vue-next'
import { authService } from '../services/auth'

// ─── Types ────────────────────────────────────────────────────────────────────
interface PipelineStatus {
  pending: number
  queued: number
  processing: number
  imported: number
  ignored: number
  errors: number
}

interface FileState {
  google_file_id: string
  file_name: string | null
  parent_folder_name: string | null
  status: string
  last_processed_at: string | null
  error_message: string | null
  user_id: number | null
}

// ─── State ────────────────────────────────────────────────────────────────────
const pipelineStatus = ref<PipelineStatus | null>(null)
const activeFiles = ref<FileState[]>([])      // PROCESSING
const queuedFiles = ref<FileState[]>([])      // QUEUED (capped to 5 for UX)
const pollingInterval = ref<ReturnType<typeof setInterval> | null>(null)
const lastRefresh = ref<Date | null>(null)
const isLoading = ref(false)
const now = ref(Date.now())  // ticker pour timers temps-réel
let tickInterval: ReturnType<typeof setInterval> | null = null

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
const authHeader = () => ({ Authorization: `Bearer ${authService.state.token}` })

const fetchStatus = async () => {
  if (isLoading.value) return
  isLoading.value = true
  try {
    // Fetch global stats
    const resp = await axios.get('/api/drive/status', { headers: authHeader() })
    pipelineStatus.value = resp.data
    lastRefresh.value = new Date()

    // Fetch active (PROCESSING) files for live list
    const [procResp, queuedResp] = await Promise.all([
      axios.get('/api/drive/files', { params: { status: 'PROCESSING', limit: 20 }, headers: authHeader() }),
      axios.get('/api/drive/files', { params: { status: 'QUEUED', limit: 5 }, headers: authHeader() }),
    ])
    activeFiles.value = procResp.data
    queuedFiles.value = queuedResp.data

    // Poll faster if active
    if (isActive.value) {
      if (!pollingInterval.value) startPolling(4000)
    } else {
      stopPolling()
      startPolling(15000)
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

onMounted(() => {
  fetchStatus()
  tickInterval = setInterval(() => { now.value = Date.now() }, 1000)
})
onUnmounted(() => {
  stopPolling()
  if (tickInterval) clearInterval(tickInterval)
})

const isFlushingZombies = ref(false)

const forceFlushZombies = async () => {
  if (isFlushingZombies.value) return
  isFlushingZombies.value = true
  try {
    await axios.post('/api/drive/retry-errors?force=true', {}, { headers: authHeader() })
    await axios.post('/api/drive/sync', {}, { headers: authHeader() })
    await fetchStatus()
  } catch (e) {
    console.error('[CVImportMonitor] Force flush failed', e)
  } finally {
    isFlushingZombies.value = false
  }
}

const formatTime = (date: Date | null) => {
  if (!date) return '—'
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

const formatElapsed = (isoDate: string | null): string => {
  if (!isoDate) return ''
  const diff = Math.floor((now.value - new Date(isoDate).getTime()) / 1000)
  if (diff < 5) return 'à l\'instant'
  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}min ${diff % 60}s`
  return `${Math.floor(diff / 3600)}h${Math.floor((diff % 3600) / 60)}min`
}

const displayName = (f: FileState): string =>
  f.file_name ? f.file_name.replace(/\.pdf$/i, '') : f.google_file_id.slice(0, 12) + '…'
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

      <!-- ── Progress bar ── -->
      <div v-if="totalFiles > 0" class="progress-section">
        <div class="progress-meta">
          <span>{{ processedFiles }} / {{ totalFiles }} fichiers traités</span>
          <div class="progress-badges">
            <span class="mini-badge badge-pending" v-if="pipelineStatus.pending > 0">
              <Clock size="10" /> {{ pipelineStatus.pending }} en attente
            </span>
            <span class="mini-badge badge-queued" v-if="pipelineStatus.queued > 0">
              <Radio size="10" /> {{ pipelineStatus.queued }} en file
            </span>
            <span class="mini-badge badge-processing" v-if="pipelineStatus.processing > 0">
              <Loader2 size="10" class="spin-icon" /> {{ pipelineStatus.processing }} en analyse
            </span>
          </div>
          <span class="progress-pct">{{ progressPct }}%</span>
        </div>
        <div class="progress-track">
          <div
            class="progress-fill fill-imported"
            :style="{ width: `${Math.round(pipelineStatus.imported / totalFiles * 100)}%` }"
          ></div>
          <div
            class="progress-fill fill-ignored"
            :style="{ width: `${Math.round(pipelineStatus.ignored / totalFiles * 100)}%` }"
          ></div>
          <div
            class="progress-fill fill-error"
            :style="{ width: `${Math.round(pipelineStatus.errors / totalFiles * 100)}%` }"
          ></div>
        </div>
        <div class="progress-legend">
          <span class="legend-item"><span class="dot dot-green"></span>Importés ({{ pipelineStatus.imported }})</span>
          <span class="legend-item"><span class="dot dot-gray"></span>Ignorés ({{ pipelineStatus.ignored }})</span>
          <span class="legend-item"><span class="dot dot-red"></span>Erreurs ({{ pipelineStatus.errors }})</span>
        </div>
      </div>

      <!-- ── Live PROCESSING list ── -->
      <div v-if="activeFiles.length > 0" class="live-section">
        <div class="live-header">
          <div class="live-title">
            <span class="live-dot"></span>
            <span>Analyse IA en cours</span>
            <span class="live-badge">{{ pipelineStatus.processing }}</span>
          </div>
        </div>
        <div class="file-list">
          <div
            v-for="file in activeFiles"
            :key="file.google_file_id"
            class="file-row file-processing"
          >
            <div class="file-icon">
              <Loader2 size="14" class="spin-icon" />
            </div>
            <div class="file-info">
              <span class="file-name">{{ displayName(file) }}</span>
              <span class="file-meta" v-if="file.parent_folder_name">
                <User size="10" /> {{ file.parent_folder_name }}
              </span>
            </div>
            <div class="file-elapsed" v-if="file.last_processed_at" :title="`Démarré il y a ${formatElapsed(file.last_processed_at)}`">
              {{ formatElapsed(file.last_processed_at) }}
            </div>
          </div>
        </div>
      </div>

      <!-- ── QUEUED files preview ── -->
      <div v-if="queuedFiles.length > 0" class="live-section live-section--queued">
        <div class="live-header">
          <div class="live-title">
            <Radio size="12" style="flex-shrink:0" />
            <span>Prochains en file Pub/Sub</span>
            <span class="live-badge badge-queued-cnt">{{ pipelineStatus.queued }}</span>
          </div>
          <button
            class="flush-btn"
            @click="forceFlushZombies"
            :disabled="isFlushingZombies"
            :title="`Forcer le déblocage de ${pipelineStatus.queued} fichier(s) bloqués`"
            aria-label="Forcer le déblocage des fichiers zombies bloqués en Pub/Sub"
          >
            <Zap size="11" :class="{ 'spin-icon': isFlushingZombies }" />
            {{ isFlushingZombies ? 'Déblocage...' : 'Forcer' }}
          </button>
        </div>
        <div class="file-list">
          <div
            v-for="file in queuedFiles"
            :key="file.google_file_id"
            class="file-row file-queued"
          >
            <div class="file-icon"><Radio size="12" /></div>
            <div class="file-info">
              <span class="file-name">{{ displayName(file) }}</span>
              <span class="file-meta" v-if="file.parent_folder_name">
                <User size="10" /> {{ file.parent_folder_name }}
              </span>
            </div>
            <div class="file-elapsed" v-if="file.last_processed_at" :title="`En queue depuis ${formatElapsed(file.last_processed_at)}`">
              {{ formatElapsed(file.last_processed_at) }}
            </div>
          </div>
          <div v-if="pipelineStatus.queued > 5" class="file-row file-more">
            <span>+ {{ pipelineStatus.queued - 5 }} autres en attente</span>
          </div>
        </div>
      </div>

      <!-- ── Alert banners ── -->
      <div v-if="pipelineStatus.errors > 0" class="alert-banner alert-error">
        <AlertTriangle size="14" />
        <span>
          <strong>{{ pipelineStatus.errors }} fichier(s)</strong> en erreur — consultez la section Drive ci-dessous.
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

/* ── Progress ── */
.progress-section { background: #f8fafc; border-radius: 12px; padding: 14px 16px; border: 1px solid #e2e8f0; }
.progress-meta {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 0.75rem; color: #64748b; margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.progress-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.mini-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
}
.badge-pending   { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
.badge-queued    { background: rgba(139,92,246,0.08); color: #7c3aed; border: 1px solid rgba(139,92,246,0.25); }
.badge-processing { background: rgba(227,25,55,0.08); color: #E31937; border: 1px solid rgba(227,25,55,0.25); }

.progress-pct { font-weight: 700; color: #1e293b; flex-shrink: 0; }
.progress-track {
  height: 8px; background: #e2e8f0; border-radius: 999px; overflow: hidden;
  display: flex;
}
.progress-fill { height: 100%; transition: width 0.6s ease; }
.fill-imported { background: #16a34a; }
.fill-ignored  { background: #94a3b8; }
.fill-error    { background: #dc2626; }

.progress-legend { display: flex; gap: 12px; margin-top: 8px; flex-wrap: wrap; }
.legend-item { display: flex; align-items: center; gap: 4px; font-size: 0.7rem; color: #64748b; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-green { background: #16a34a; }
.dot-gray  { background: #94a3b8; }
.dot-red   { background: #dc2626; }

/* ── Live sections ── */
.live-section {
  border-radius: 12px; overflow: hidden;
  border: 1px solid rgba(227,25,55,0.2);
  background: rgba(227,25,55,0.03);
}
.live-section--queued {
  border-color: rgba(139,92,246,0.2);
  background: rgba(139,92,246,0.03);
}

.live-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  background: rgba(255,255,255,0.6);
}
.live-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.78rem; font-weight: 700; color: #E31937;
}
.live-section--queued .live-title { color: #7c3aed; }

.live-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #E31937;
  animation: dot-pulse 1s ease-in-out infinite;
}

.live-badge {
  padding: 1px 7px; border-radius: 20px;
  background: rgba(227,25,55,0.12); color: #E31937;
  font-size: 0.68rem; font-weight: 800;
}
.badge-queued-cnt {
  background: rgba(139,92,246,0.12); color: #7c3aed;
}

.file-list { display: flex; flex-direction: column; }

.file-row {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 14px;
  border-bottom: 1px solid rgba(0,0,0,0.04);
  transition: background 0.15s;
}
.file-row:last-child { border-bottom: none; }
.file-row:hover { background: rgba(255,255,255,0.7); }

.file-icon {
  width: 22px; height: 22px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.file-processing .file-icon { background: rgba(227,25,55,0.1); color: #E31937; }
.file-queued .file-icon     { background: rgba(139,92,246,0.1); color: #7c3aed; }

.file-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.file-name {
  font-size: 0.82rem; font-weight: 600; color: #1e293b;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.file-meta {
  display: flex; align-items: center; gap: 4px;
  font-size: 0.68rem; color: #94a3b8;
}

.file-elapsed {
  font-size: 0.68rem; font-weight: 700; color: #94a3b8;
  flex-shrink: 0; font-variant-numeric: tabular-nums;
  background: #f1f5f9; padding: 2px 6px; border-radius: 6px;
}

.file-more {
  font-size: 0.75rem; color: #94a3b8; font-style: italic;
  justify-content: center; padding: 8px 14px;
}

/* ── Alert banners ── */
.alert-banner {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 14px; border-radius: 10px;
  font-size: 0.82rem; line-height: 1.5;
}
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

/* ── Force flush button ── */
.flush-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px; border-radius: 8px;
  background: rgba(139,92,246,0.15);
  color: #7c3aed;
  border: 1px solid rgba(139,92,246,0.35);
  font-size: 0.72rem; font-weight: 700;
  cursor: pointer; transition: all 0.2s;
  animation: pulse-flush 2s ease-in-out infinite;
}
.flush-btn:hover:not(:disabled) {
  background: rgba(139,92,246,0.25);
  border-color: rgba(139,92,246,0.6);
}
.flush-btn:disabled { opacity: 0.5; cursor: not-allowed; animation: none; }
@keyframes pulse-flush {
  0%,100% { box-shadow: 0 0 0 0 rgba(139,92,246,0); }
  50%      { box-shadow: 0 0 0 4px rgba(139,92,246,0.2); }
}

.spin-icon { animation: spin 1.5s linear infinite; }
</style>
