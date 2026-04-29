<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import axios from 'axios'
import {
  Activity, RefreshCw, BarChart2, CheckCircle2, AlertTriangle,
  XCircle, Clock, Zap, FolderOpen, Users, ArrowLeft, Loader2,
  ShieldCheck, Radio, Database, Network
} from 'lucide-vue-next'
import { authService } from '../services/auth'
import PageHeader from '../components/ui/PageHeader.vue'
import DriveAdminPanel from '../components/DriveAdminPanel.vue'

// ── Types ──────────────────────────────────────────────────────────────────────
interface KPIMetric { value: number; pct: number; ok: number; total: number; status: string; unit: string }
interface IngestionStats {
  total_files: number; imported: number; errors: number
  pending: number; queued: number; processing: number; ignored: number
  freshness_hours: number | null
  metrics: Record<string, KPIMetric>
  score: number; grade: string
  issues: string[]; recommendation: string; computed_at: string
}
interface FolderKPI {
  folder_id: number; folder_name: string | null; tag: string
  total: number; imported: number; errors: number
  pending: number; queued: number; processing: number; ignored: number
  import_rate_pct: number; error_rate_pct: number; user_link_rate_pct: number
  avg_processing_ms: number | null; last_import_at: string | null; status: string
}

// ── State ──────────────────────────────────────────────────────────────────────
const stats = ref<IngestionStats | null>(null)
const folderKpis = ref<FolderKPI[]>([])
const isLoadingStats = ref(false)
const isLoadingFolders = ref(false)
const isRunningBatch = ref(false)
const isRunningGate = ref(false)
const batchResult = ref<any>(null)
const gateResult = ref<any>(null)
const lastRefresh = ref<Date | null>(null)
const pollingId = ref<ReturnType<typeof setInterval> | null>(null)

const authHeader = () => ({ Authorization: `Bearer ${authService.state.token}` })

const gradeColor = computed(() => {
  const g = stats.value?.grade
  if (g === 'A') return '#16a34a'
  if (g === 'B') return '#65a30d'
  if (g === 'C') return '#d97706'
  if (g === 'D') return '#ea580c'
  return '#dc2626'
})

const metricStatusClass = (status: string) => {
  if (status === 'critical') return 'metric-critical'
  if (status === 'warning') return 'metric-warning'
  return 'metric-ok'
}

const folderStatusClass = (status: string) => {
  if (status === 'critical') return 'row-critical'
  if (status === 'warning') return 'row-warning'
  return ''
}

const formatMs = (ms: number | null) => {
  if (!ms) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const formatDate = (iso: string | null) => {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const pctBarWidth = (metric: KPIMetric) => {
  if (metric.unit === 's') return Math.min(100, metric.pct) + '%'
  return metric.pct + '%'
}

// ── Data Fetching ──────────────────────────────────────────────────────────────
const fetchAll = async () => {
  isLoadingStats.value = true
  isLoadingFolders.value = true
  try {
    const [statsRes, foldersRes] = await Promise.all([
      axios.get('/api/drive/ingestion/stats', { headers: authHeader() }),
      axios.get('/api/drive/ingestion/folder-kpis', { headers: authHeader() }),
    ])
    stats.value = statsRes.data
    folderKpis.value = foldersRes.data
    lastRefresh.value = new Date()
  } catch (e) {
    console.error('[AdminDriveIngestion] fetch failed', e)
  } finally {
    isLoadingStats.value = false
    isLoadingFolders.value = false
  }
}

onMounted(() => {
  fetchAll()
  pollingId.value = setInterval(fetchAll, 30000)
})
onUnmounted(() => { if (pollingId.value) clearInterval(pollingId.value) })

// ── Actions ────────────────────────────────────────────────────────────────────
const runBatchRetry = async () => {
  if (isRunningBatch.value) return
  isRunningBatch.value = true
  batchResult.value = null
  try {
    const res = await axios.post('/api/drive/ingestion/batch-retry', {}, { headers: authHeader() })
    batchResult.value = res.data
    await fetchAll()
  } catch (e: any) {
    batchResult.value = { error: e.response?.data?.detail || 'Erreur inconnue' }
  } finally {
    isRunningBatch.value = false
  }
}

const runQualityGate = async () => {
  if (isRunningGate.value) return
  isRunningGate.value = true
  gateResult.value = null
  try {
    const res = await axios.post('/api/drive/ingestion/quality-gate-batch', {}, { headers: authHeader() })
    gateResult.value = res.data
    await fetchAll()
  } catch (e: any) {
    gateResult.value = { error: e.response?.data?.detail || 'Erreur inconnue' }
  } finally {
    isRunningGate.value = false
  }
}

const isInvalidatingCache = ref(false)
const runInvalidateCache = async () => {
  if (!confirm("Voulez-vous vraiment invalider le cache Redis ? (L'arbre Drive sera reconstruit)")) return
  if (isInvalidatingCache.value) return
  isInvalidatingCache.value = true
  batchResult.value = null
  try {
    const res = await axios.post('/api/drive/folders/invalidate-cache', {}, { headers: authHeader() })
    batchResult.value = { message: `Cache invalidé avec succès (${res.data.keys_deleted} clés supprimées)` }
  } catch (e: any) {
    batchResult.value = { error: e.response?.data?.detail || "Erreur lors de l'invalidation du cache" }
  } finally {
    isInvalidatingCache.value = false
  }
}

const isRebuildingTree = ref(false)
const runRebuildTree = async () => {
  if (!confirm("Voulez-vous lancer la reconstruction complète de l'arbre ? Cela vérifiera chaque dossier parent sans modifier le statut des CVs actuels.")) return
  if (isRebuildingTree.value) return
  isRebuildingTree.value = true
  batchResult.value = null
  try {
    const res = await axios.post('/api/drive/folders/rebuild-tree', {}, { headers: authHeader() })
    batchResult.value = { message: res.data.message }
  } catch (e: any) {
    batchResult.value = { error: e.response?.data?.detail || "Erreur lors de la reconstruction de l'arbre" }
  } finally {
    isRebuildingTree.value = false
  }
}

const runSync = async () => {
  try {
    await axios.post('/api/drive/sync', {}, { headers: authHeader() })
    setTimeout(fetchAll, 2000)
  } catch (e) { console.error(e) }
}
</script>

<template>
  <div class="page-wrapper fade-in">
    <PageHeader
      title="Supervision Drive Ingestion"
      subtitle="Supervision complète du pipeline Drive → CV · KPIs · Gestion des Sources"
      :icon="BarChart2"
    />

    <!-- ── Toolbar ── -->
    <div class="toolbar">
      <button class="btn-icon" @click="fetchAll" :disabled="isLoadingStats" aria-label="Rafraîchir">
        <RefreshCw size="15" :class="{ spin: isLoadingStats }" />
        <span>{{ lastRefresh ? `Rafraîchi à ${lastRefresh.toLocaleTimeString('fr-FR')}` : 'Chargement…' }}</span>
      </button>
      <div class="toolbar-actions">
        <button class="btn-action btn-sync" @click="runSync" aria-label="Forcer sync Drive">
          <Radio size="14" /> Forcer Sync Drive
        </button>
        <button class="btn-action btn-sync" @click="runRebuildTree" :disabled="isRebuildingTree || stats?.is_rebuilding_tree" aria-label="Reconstruire l'arbre">
          <Network size="14" :class="{ spin: isRebuildingTree || stats?.is_rebuilding_tree }" />
          {{ isRebuildingTree || stats?.is_rebuilding_tree ? 'Reconstruction…' : "Reconstruire l'Arbre" }}
        </button>
        <button class="btn-action btn-gate" @click="runInvalidateCache" :disabled="isInvalidatingCache" aria-label="Invalider Cache">
          <Database size="14" :class="{ spin: isInvalidatingCache }" />
          {{ isInvalidatingCache ? 'Invalidation…' : 'Invalider Cache' }}
        </button>
        <button class="btn-action btn-retry" @click="runBatchRetry" :disabled="isRunningBatch" aria-label="Retry erreurs">
          <Zap size="14" :class="{ spin: isRunningBatch }" />
          {{ isRunningBatch ? 'En cours…' : 'Retry Erreurs' }}
        </button>
        <button class="btn-action btn-gate" @click="runQualityGate" :disabled="isRunningGate" aria-label="Quality Gate Batch">
          <ShieldCheck size="14" :class="{ spin: isRunningGate }" />
          {{ isRunningGate ? 'Analyse…' : 'Quality Gate Batch' }}
        </button>
      </div>
    </div>

    <!-- ── Batch result banners ── -->
    <div v-if="stats?.is_rebuilding_tree" class="result-banner banner-warning">
      <Loader2 size="14" class="spin" style="display:inline-block; vertical-align: middle; margin-right: 5px;" />
      Reconstruction complète de l'arbre en cours sur Google Drive... (Pendant ce temps, les CVs restent intacts)
    </div>

    <div v-if="batchResult" class="result-banner" :class="batchResult.error ? 'banner-error' : 'banner-ok'">
      <template v-if="batchResult.error">❌ {{ batchResult.error }}</template>
      <template v-else>✅ {{ batchResult.message }}</template>
    </div>
    <div v-if="gateResult" class="result-banner" :class="gateResult.error ? 'banner-error' : 'banner-ok'">
      <template v-if="gateResult.error">❌ {{ gateResult.error }}</template>
      <template v-else>
        🛡️ {{ gateResult.message }}
        <span v-if="gateResult.reason_breakdown" class="breakdown">
          · user_id manquant: {{ gateResult.reason_breakdown.user_id_manquant }}
          · nommage: {{ gateResult.reason_breakdown.nommage_manquant }}
          · erreurs: {{ gateResult.reason_breakdown.erreur_persistante }}
        </span>
      </template>
    </div>

    <div v-if="isLoadingStats && !stats" class="loading-state">
      <Loader2 size="32" class="spin" />
      <p>Calcul des KPIs en cours…</p>
    </div>

    <template v-else-if="stats">
      <!-- ── Grade + Volumes ── -->
      <div class="top-row">
        <div class="grade-card">
          <div class="grade-circle" :style="{ borderColor: gradeColor, color: gradeColor }">
            {{ stats.grade }}
          </div>
          <div class="grade-info">
            <div class="grade-score">Score {{ stats.score }}/100</div>
            <div class="grade-recommendation">{{ stats.recommendation }}</div>
          </div>
        </div>

        <div class="volumes-grid">
          <div class="vol-item vol-total"><Database size="16" /><span class="vol-n">{{ stats.total_files }}</span><span class="vol-l">Total</span></div>
          <div class="vol-item vol-ok"><CheckCircle2 size="16" /><span class="vol-n">{{ stats.imported }}</span><span class="vol-l">Importés</span></div>
          <div class="vol-item vol-err"><XCircle size="16" /><span class="vol-n">{{ stats.errors }}</span><span class="vol-l">Erreurs</span></div>
          <div class="vol-item vol-pend"><Clock size="16" /><span class="vol-n">{{ stats.pending }}</span><span class="vol-l">En attente</span></div>
          <div class="vol-item vol-queue"><Radio size="16" /><span class="vol-n">{{ stats.queued }}</span><span class="vol-l">En file</span></div>
          <div class="vol-item vol-proc"><Loader2 size="16" class="spin-slow" /><span class="vol-n">{{ stats.processing }}</span><span class="vol-l">En cours</span></div>
        </div>
      </div>

      <!-- ── Issues ── -->
      <div v-if="stats.issues.length > 0" class="issues-panel">
        <div class="issues-header"><AlertTriangle size="15" /> {{ stats.issues.length }} problème(s) détecté(s)</div>
        <ul class="issues-list">
          <li v-for="issue in stats.issues" :key="issue">{{ issue }}</li>
        </ul>
      </div>
      <div v-else class="issues-panel issues-ok">
        <CheckCircle2 size="15" /> Data quality satisfaisante — aucune anomalie détectée.
      </div>

      <!-- ── KPI Metrics ── -->
      <div class="section-card">
        <div class="section-header"><Activity size="17" /> Métriques de Data Quality</div>
        <div class="metrics-grid">
          <div v-for="(metric, label) in stats.metrics" :key="label" class="metric-row">
            <div class="metric-label-row">
              <span class="metric-label">{{ label }}</span>
              <span class="metric-value" :class="metricStatusClass(metric.status)">
                {{ metric.unit === 's' ? metric.value + 's' : metric.pct + '%' }}
                <span class="metric-counts" v-if="metric.unit !== 's'">({{ metric.ok }}/{{ metric.total }})</span>
              </span>
            </div>
            <div class="metric-bar-track">
              <div
                class="metric-bar-fill"
                :class="metricStatusClass(metric.status)"
                :style="{ width: pctBarWidth(metric) }"
              />
            </div>
          </div>
        </div>
        <div class="freshness-row" v-if="stats.freshness_hours !== null">
          <Clock size="13" />
          Dernière ingestion il y a <strong>{{ stats.freshness_hours }}h</strong>
        </div>
      </div>

      <!-- ── Folder KPIs ── -->
      <div class="section-card">
        <div class="section-header"><FolderOpen size="17" /> KPIs par Agence / Dossier</div>
        <div v-if="isLoadingFolders" class="table-loading"><Loader2 size="18" class="spin" /></div>
        <div v-else-if="folderKpis.length === 0" class="table-empty">
          <Users size="24" /> Aucun dossier Drive configuré.
        </div>
        <div v-else class="table-wrapper">
          <table class="kpi-table">
            <thead>
              <tr>
                <th>Dossier / Agence</th>
                <th class="num">Total</th>
                <th class="num">Importés</th>
                <th class="num">Erreurs</th>
                <th class="num">Taux import</th>
                <th class="num">Liaison user</th>
                <th class="num">Durée moy.</th>
                <th class="num">Dernière import</th>
                <th>Statut</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in folderKpis" :key="f.folder_id" :class="folderStatusClass(f.status)">
                <td class="folder-name">
                  <FolderOpen size="13" />
                  <span>{{ f.folder_name || f.tag }}</span>
                  <span class="tag-chip">{{ f.tag }}</span>
                </td>
                <td class="num">{{ f.total }}</td>
                <td class="num text-green">{{ f.imported }}</td>
                <td class="num text-red">{{ f.errors }}</td>
                <td class="num">
                  <span :class="f.import_rate_pct < 75 ? 'text-red' : f.import_rate_pct < 90 ? 'text-orange' : 'text-green'">
                    {{ f.import_rate_pct }}%
                  </span>
                </td>
                <td class="num">
                  <span :class="f.user_link_rate_pct < 80 ? 'text-red' : f.user_link_rate_pct < 90 ? 'text-orange' : 'text-green'">
                    {{ f.imported > 0 ? f.user_link_rate_pct + '%' : '—' }}
                  </span>
                </td>
                <td class="num">{{ formatMs(f.avg_processing_ms) }}</td>
                <td class="num">{{ formatDate(f.last_import_at) }}</td>
                <td>
                  <span class="status-pill" :class="`pill-${f.status}`">
                    {{ f.status === 'ok' ? '✓ OK' : f.status === 'warning' ? '⚠ Attention' : '✕ Critique' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      
      <!-- ── Folder Settings & DLQ Management ── -->
      <DriveAdminPanel />

    </template>
  </div>
</template>

<style scoped>
.page-wrapper { max-width: 1300px; margin: 0 auto; padding: 2rem; display: flex; flex-direction: column; gap: 1.5rem; }
.fade-in { animation: fadeIn 0.35s ease forwards; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* ── Toolbar ── */
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.btn-icon { display: flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.7); border: 1px solid #e2e8f0; border-radius: 10px; padding: 6px 14px; font-size: 0.78rem; color: #64748b; cursor: pointer; transition: all 0.2s; }
.btn-icon:hover { background: #f1f5f9; }
.toolbar-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.btn-action { display: inline-flex; align-items: center; gap: 7px; padding: 8px 16px; border-radius: 10px; font-size: 0.82rem; font-weight: 700; cursor: pointer; border: none; transition: all 0.2s; }
.btn-action:disabled { opacity: 0.55; cursor: not-allowed; }
.btn-sync { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }
.btn-sync:hover:not(:disabled) { background: #bae6fd; }
.btn-retry { background: rgba(139,92,246,0.1); color: #7c3aed; border: 1px solid rgba(139,92,246,0.3); }
.btn-retry:hover:not(:disabled) { background: rgba(139,92,246,0.2); }
.btn-gate { background: rgba(16,163,74,0.1); color: #166534; border: 1px solid rgba(16,163,74,0.3); }
.btn-gate:hover:not(:disabled) { background: rgba(16,163,74,0.2); }

/* ── Banners ── */
.result-banner { padding: 10px 16px; border-radius: 10px; font-size: 0.83rem; font-weight: 600; }
.banner-ok { background: rgba(16,163,74,0.08); color: #166534; border: 1px solid rgba(16,163,74,0.25); }
.banner-error { background: rgba(220,38,38,0.08); color: #b91c1c; border: 1px solid rgba(220,38,38,0.25); }
.breakdown { font-weight: 400; opacity: 0.8; }

/* ── Loading ── */
.loading-state { text-align: center; padding: 3rem; color: #94a3b8; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.loading-state p { font-size: 0.9rem; margin: 0; }

/* ── Top Row ── */
.top-row { display: grid; grid-template-columns: auto 1fr; gap: 1.5rem; align-items: center; }
@media (max-width: 768px) { .top-row { grid-template-columns: 1fr; } }

.grade-card { display: flex; align-items: center; gap: 20px; background: rgba(255,255,255,0.8); border-radius: 20px; border: 1px solid rgba(255,255,255,0.6); box-shadow: 0 4px 20px rgba(0,0,0,0.06); padding: 1.5rem 2rem; }
.grade-circle { width: 72px; height: 72px; border-radius: 50%; border: 4px solid; display: flex; align-items: center; justify-content: center; font-size: 2rem; font-weight: 900; flex-shrink: 0; }
.grade-score { font-size: 1rem; font-weight: 700; color: #1e293b; }
.grade-recommendation { font-size: 0.78rem; color: #64748b; margin-top: 4px; max-width: 200px; }

.volumes-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
@media (max-width: 900px) { .volumes-grid { grid-template-columns: repeat(3, 1fr); } }
.vol-item { background: rgba(255,255,255,0.8); border-radius: 14px; border: 1px solid rgba(255,255,255,0.6); box-shadow: 0 2px 10px rgba(0,0,0,0.05); padding: 14px; display: flex; flex-direction: column; align-items: center; gap: 4px; }
.vol-n { font-size: 1.5rem; font-weight: 800; color: #1e293b; line-height: 1; }
.vol-l { font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; }
.vol-ok { border-color: rgba(16,163,74,0.2); } .vol-ok .vol-n { color: #16a34a; }
.vol-err { border-color: rgba(220,38,38,0.2); } .vol-err .vol-n { color: #dc2626; }
.vol-queue { border-color: rgba(139,92,246,0.2); } .vol-queue .vol-n { color: #7c3aed; }
.vol-proc { border-color: rgba(227,25,55,0.2); } .vol-proc .vol-n { color: #E31937; }

/* ── Issues ── */
.issues-panel { background: rgba(255,255,255,0.75); border-radius: 14px; padding: 14px 18px; border: 1px solid rgba(220,38,38,0.2); display: flex; flex-direction: column; gap: 6px; }
.issues-header { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; font-weight: 700; color: #b91c1c; }
.issues-list { margin: 0; padding-left: 18px; list-style: disc; }
.issues-list li { font-size: 0.8rem; color: #7f1d1d; padding: 2px 0; }
.issues-ok { border-color: rgba(16,163,74,0.25); flex-direction: row; align-items: center; gap: 8px; font-size: 0.82rem; font-weight: 600; color: #166534; }

/* ── Section Cards ── */
.section-card { background: rgba(255,255,255,0.75); backdrop-filter: blur(16px); border-radius: 20px; border: 1px solid rgba(255,255,255,0.6); box-shadow: 0 4px 20px rgba(0,0,0,0.06); overflow: hidden; }
.section-header { display: flex; align-items: center; gap: 10px; font-size: 0.9rem; font-weight: 700; color: #1e293b; padding: 1rem 1.5rem; border-bottom: 1px solid rgba(0,0,0,0.06); background: rgba(255,255,255,0.5); }

/* ── Metrics ── */
.metrics-grid { display: flex; flex-direction: column; gap: 14px; padding: 1.25rem 1.5rem; }
.metric-row { display: flex; flex-direction: column; gap: 5px; }
.metric-label-row { display: flex; justify-content: space-between; align-items: center; }
.metric-label { font-size: 0.82rem; font-weight: 600; color: #475569; }
.metric-value { font-size: 0.82rem; font-weight: 800; }
.metric-counts { font-weight: 400; opacity: 0.7; margin-left: 4px; }
.metric-ok { color: #16a34a; }
.metric-warning { color: #d97706; }
.metric-critical { color: #dc2626; }
.metric-bar-track { height: 6px; background: #e2e8f0; border-radius: 999px; overflow: hidden; }
.metric-bar-fill { height: 100%; border-radius: 999px; transition: width 0.6s ease; }
.metric-bar-fill.metric-ok { background: #16a34a; }
.metric-bar-fill.metric-warning { background: #d97706; }
.metric-bar-fill.metric-critical { background: #dc2626; }
.freshness-row { display: flex; align-items: center; gap: 6px; font-size: 0.78rem; color: #64748b; padding: 0 1.5rem 1rem; }

/* ── Table ── */
.table-wrapper { overflow-x: auto; padding: 0 0 0.5rem; }
.table-loading { padding: 2rem; text-align: center; }
.table-empty { padding: 2.5rem; text-align: center; color: #94a3b8; display: flex; flex-direction: column; align-items: center; gap: 10px; font-size: 0.85rem; }
.kpi-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.kpi-table th { padding: 10px 14px; text-align: left; font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; border-bottom: 1px solid #e2e8f0; white-space: nowrap; background: rgba(248,250,252,0.8); }
.kpi-table th.num { text-align: right; }
.kpi-table td { padding: 10px 14px; border-bottom: 1px solid rgba(0,0,0,0.04); color: #1e293b; }
.kpi-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.kpi-table tr:hover td { background: rgba(255,255,255,0.7); }
.kpi-table tr.row-critical td { background: rgba(220,38,38,0.04); }
.kpi-table tr.row-warning td { background: rgba(234,179,8,0.04); }
.folder-name { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.tag-chip { font-size: 0.65rem; background: #f1f5f9; color: #64748b; padding: 1px 6px; border-radius: 6px; font-weight: 600; border: 1px solid #e2e8f0; }
.text-green { color: #16a34a; font-weight: 700; }
.text-red { color: #dc2626; font-weight: 700; }
.text-orange { color: #d97706; font-weight: 700; }

.status-pill { display: inline-flex; align-items: center; padding: 2px 10px; border-radius: 20px; font-size: 0.7rem; font-weight: 700; white-space: nowrap; }
.pill-ok { background: rgba(16,163,74,0.1); color: #166534; border: 1px solid rgba(16,163,74,0.25); }
.pill-warning { background: rgba(234,179,8,0.1); color: #92400e; border: 1px solid rgba(234,179,8,0.3); }
.pill-critical { background: rgba(220,38,38,0.1); color: #991b1b; border: 1px solid rgba(220,38,38,0.25); }

/* ── Animations ── */
.spin { animation: spin 1s linear infinite; }
.spin-slow { animation: spin 2s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
