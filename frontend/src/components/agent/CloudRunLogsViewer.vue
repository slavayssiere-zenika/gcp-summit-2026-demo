<template>
  <div class="logs-viewer">
    <!-- Header toolbar -->
    <div class="logs-header">
      <div class="logs-header-left">
        <span class="logs-icon"><Terminal size="15" /></span>
        <span class="logs-title">Cloud Run Logs</span>
        <span class="logs-service-badge">{{ serviceName }}</span>
        <span class="logs-count">{{ filteredLogs.length }} entrée{{ filteredLogs.length > 1 ? 's' : '' }}</span>
      </div>
      <div class="logs-header-right">
        <!-- Severity filters -->
        <div class="severity-filters">
          <button
            v-for="sev in severityOptions"
            :key="sev.key"
            :class="['sev-btn', sev.key, { active: activeSeverities.has(sev.key) }]"
            @click="toggleSeverity(sev.key)"
            :aria-label="`Filtrer par ${sev.label}`"
          >
            <span class="sev-dot" :class="sev.key"></span>{{ sev.label }}
            <span class="sev-count">{{ countBySeverity(sev.key) }}</span>
          </button>
        </div>
        <!-- Collapse all -->
        <button class="toolbar-btn" @click="collapseAll" aria-label="Réduire tous les logs">
          <ChevronsUpDown size="13" /> Réduire
        </button>
      </div>
    </div>

    <!-- Summary stats bar -->
    <div class="stats-bar">
      <div class="stat-item">
        <Clock size="11" />
        <span>{{ timeRange }}</span>
      </div>
      <div class="stat-item">
        <Activity size="11" />
        <span>{{ uniqueEndpoints.length }} endpoint{{ uniqueEndpoints.length > 1 ? 's' : '' }}</span>
      </div>
      <div class="stat-item" v-if="errorCount > 0">
        <AlertTriangle size="11" class="stat-error" />
        <span class="stat-error">{{ errorCount }} erreur{{ errorCount > 1 ? 's' : '' }}</span>
      </div>
    </div>

    <!-- Log rows -->
    <div class="logs-table">
      <div class="logs-table-head">
        <span class="col-sev">Sév</span>
        <span class="col-time">Horodatage</span>
        <span class="col-method">Méthode</span>
        <span class="col-endpoint">Endpoint</span>
        <span class="col-status">Status</span>
        <span class="col-duration">Durée</span>
        <span class="col-expand"></span>
      </div>

      <div class="logs-body">
        <template v-for="(log, idx) in filteredLogs" :key="idx">
          <!-- Compact row -->
          <button
            :class="['log-row', severityClass(log), { 'row-expanded': expandedRows.has(idx) }]"
            @click="toggleRow(idx)"
            :aria-label="`Log ${idx + 1} — ${getMethod(log)} ${getEndpoint(log)}`"
          >
            <span class="col-sev">
              <span :class="['sev-indicator', severityClass(log)]"></span>
            </span>
            <span class="col-time">{{ formatTime(log.timestamp) }}</span>
            <span class="col-method">
              <span :class="['method-badge', methodClass(getMethod(log))]">{{ getMethod(log) || '—' }}</span>
            </span>
            <span class="col-endpoint" :title="isHttpLog(log) ? getEndpoint(log) : getMessageText(log)">
              <template v-if="isHttpLog(log)">
                {{ truncateEndpoint(getEndpoint(log)) }}
              </template>
              <template v-else-if="getMessageText(log)">
                <span class="message-text">{{ truncateEndpoint(getMessageText(log)) }}</span>
              </template>
              <template v-else>
                <span class="status-empty">—</span>
              </template>
            </span>
            <span class="col-status">
              <span v-if="getStatus(log)" :class="['status-badge', statusClass(getStatus(log))]">{{ getStatus(log) }}</span>
              <span v-else class="status-empty">—</span>
            </span>
            <span class="col-duration">
              <span v-if="getDuration(log)" class="duration-val">{{ formatDuration(getDuration(log)) }}</span>
              <span v-else class="status-empty">—</span>
            </span>
            <span class="col-expand">
              <ChevronDown size="12" :class="['expand-chevron', { open: expandedRows.has(idx) }]" />
            </span>
          </button>

          <!-- Expanded detail row -->
          <Transition name="log-slide">
            <div v-if="expandedRows.has(idx)" class="log-detail">
              <div class="detail-grid">
                <template v-if="typeof log.message === 'object' && log.message">
                  <div v-for="(val, key) in log.message" :key="key" class="detail-kv">
                    <span class="detail-key">{{ key }}</span>
                    <span class="detail-val">{{ val }}</span>
                  </div>
                </template>
                <template v-else>
                  <div class="detail-kv">
                    <span class="detail-key">severity</span>
                    <span class="detail-val">{{ log.severity || 'n/a' }}</span>
                  </div>
                  <div class="detail-kv">
                    <span class="detail-key">timestamp</span>
                    <span class="detail-val">{{ log.timestamp }}</span>
                  </div>
                  <div class="detail-kv">
                    <span class="detail-key">service</span>
                    <span class="detail-val">{{ log.cloud_run_service }}</span>
                  </div>
                  <div v-if="log.message" class="detail-kv full-width">
                    <span class="detail-key">message</span>
                    <span class="detail-val">{{ log.message }}</span>
                  </div>
                </template>
              </div>
              <button class="copy-detail-btn" @click.stop="copyLog(log, idx)" :aria-label="`Copier le log ${idx + 1}`">
                <template v-if="copiedIdx === idx">
                  <CheckCircle2 size="11" /> Copié !
                </template>
                <template v-else>
                  <Copy size="11" /> Copier JSON
                </template>
              </button>
            </div>
          </Transition>
        </template>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="filteredLogs.length === 0" class="logs-empty">
      <Info size="16" />
      <span>Aucun log correspondant aux filtres actifs</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Terminal, ChevronDown, ChevronsUpDown, Clock, Activity,
  AlertTriangle, Info, Copy, CheckCircle2
} from 'lucide-vue-next'

interface LogEntry {
  timestamp: string
  severity: string | null
  cloud_run_service: string
  message: any
}

const props = defineProps<{ logs: LogEntry[] }>()

// ── State ─────────────────────────────────────────────────────
const expandedRows = ref(new Set<number>())
const copiedIdx = ref<number | null>(null)
const activeSeverities = ref(new Set(['INFO', 'WARNING', 'ERROR', 'DEFAULT', 'null']))

const severityOptions = [
  { key: 'INFO',    label: 'INFO' },
  { key: 'WARNING', label: 'WARN' },
  { key: 'ERROR',   label: 'ERR'  },
]

// ── Helpers ───────────────────────────────────────────────────
const getSeverity = (log: LogEntry): string => {
  if (log.severity) return log.severity
  if (typeof log.message === 'object' && log.message?.levelname) return log.message.levelname
  return 'DEFAULT'
}

const getMethod = (log: LogEntry): string => {
  if (typeof log.message === 'object' && log.message) return log.message['http.method'] || ''
  return ''
}

const getEndpoint = (log: LogEntry): string => {
  if (typeof log.message === 'object' && log.message) {
    const url = log.message['http.url'] || ''
    try { return new URL(url).pathname } catch { return url }
  }
  return ''
}

/** Retourne le texte du message pour les logs non-HTTP (init, erreurs, messages libres) */
const getMessageText = (log: LogEntry): string => {
  if (typeof log.message === 'string' && log.message) return log.message
  if (typeof log.message === 'object' && log.message) {
    // Log structuré mais sans URL HTTP → affiche message.message
    if (!log.message['http.url'] && log.message['message']) return log.message['message']
  }
  return ''
}

/** Vrai si ce log est un log HTTP standard (avec url + méthode) */
const isHttpLog = (log: LogEntry): boolean => {
  return typeof log.message === 'object' && !!log.message?.['http.url']
}

const getStatus = (log: LogEntry): number | null => {
  if (typeof log.message === 'object' && log.message) return log.message['http.status_code'] || null
  return null
}

const getDuration = (log: LogEntry): number | null => {
  if (typeof log.message === 'object' && log.message) return log.message['http.duration_s'] || null
  return null
}

const formatTime = (ts: string): string => {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 })
  } catch { return ts }
}

const formatDuration = (d: number): string => {
  if (d < 0.001) return `${(d * 1000000).toFixed(0)}µs`
  if (d < 1) return `${(d * 1000).toFixed(1)}ms`
  return `${d.toFixed(2)}s`
}

const truncateEndpoint = (ep: string): string => ep.length > 45 ? '…' + ep.slice(-43) : ep

const severityClass = (log: LogEntry): string => {
  const s = getSeverity(log)
  if (s === 'ERROR' || s === 'CRITICAL') return 'sev-error'
  if (s === 'WARNING') return 'sev-warning'
  if (s === 'INFO') return 'sev-info'
  return 'sev-default'
}

const methodClass = (m: string): string => {
  switch (m) {
    case 'GET': return 'method-get'
    case 'POST': return 'method-post'
    case 'PUT': return 'method-put'
    case 'DELETE': return 'method-delete'
    case 'PATCH': return 'method-patch'
    default: return 'method-other'
  }
}

const statusClass = (s: number | null): string => {
  if (!s) return ''
  if (s < 300) return 'status-2xx'
  if (s < 400) return 'status-3xx'
  if (s < 500) return 'status-4xx'
  return 'status-5xx'
}

// ── Computed ──────────────────────────────────────────────────
const serviceName = computed(() =>
  props.logs[0]?.cloud_run_service || 'cloud-run'
)

const filteredLogs = computed(() =>
  props.logs.filter(log => {
    const sev = getSeverity(log)
    return activeSeverities.value.has(sev) || activeSeverities.value.has('DEFAULT')
  })
)

const countBySeverity = (key: string): number =>
  props.logs.filter(l => getSeverity(l) === key).length

const errorCount = computed(() =>
  props.logs.filter(l => ['ERROR', 'CRITICAL'].includes(getSeverity(l))).length
)

const uniqueEndpoints = computed(() =>
  [...new Set(props.logs.map(l => getEndpoint(l)).filter(Boolean))]
)

const timeRange = computed(() => {
  if (props.logs.length < 2) return 'instantané'
  const times = props.logs.map(l => new Date(l.timestamp).getTime()).filter(t => !isNaN(t))
  const delta = Math.abs(Math.max(...times) - Math.min(...times))
  const mins = Math.floor(delta / 60000)
  const secs = Math.floor((delta % 60000) / 1000)
  return mins > 0 ? `${mins}min ${secs}s` : `${secs}s`
})

// ── Actions ───────────────────────────────────────────────────
const toggleRow = (idx: number) => {
  if (expandedRows.value.has(idx)) expandedRows.value.delete(idx)
  else expandedRows.value.add(idx)
}

const collapseAll = () => expandedRows.value.clear()

const toggleSeverity = (key: string) => {
  if (activeSeverities.value.has(key)) activeSeverities.value.delete(key)
  else activeSeverities.value.add(key)
}

const copyLog = async (log: LogEntry, idx: number) => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(log, null, 2))
    copiedIdx.value = idx
    setTimeout(() => { copiedIdx.value = null }, 2000)
  } catch { /* ignore */ }
}
</script>

<style scoped>
/* ── Container ──────────────────────────────────────────────── */
.logs-viewer {
  margin-top: 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  background: #0f172a;
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
}

/* ── Header ─────────────────────────────────────────────────── */
.logs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #1e293b;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  gap: 8px;
  flex-wrap: wrap;
}

.logs-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logs-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.logs-icon {
  display: inline-flex;
  align-items: center;
  color: #e31937;
}

.logs-title {
  font-size: 0.75rem;
  font-weight: 700;
  color: #e2e8f0;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.logs-service-badge {
  background: rgba(227, 25, 55, 0.15);
  border: 1px solid rgba(227, 25, 55, 0.3);
  color: #f87171;
  font-size: 0.68rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.03em;
}

.logs-count {
  font-size: 0.68rem;
  color: #64748b;
  font-weight: 500;
}

/* ── Severity filter buttons ─────────────────────────────────── */
.severity-filters {
  display: flex;
  gap: 4px;
}

.sev-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  cursor: pointer;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  color: #64748b;
  transition: all 0.15s;
  font-family: inherit;
  letter-spacing: 0.04em;
}

.sev-btn.active.INFO    { background: rgba(16,185,129,0.15); border-color: rgba(16,185,129,0.3); color: #34d399; }
.sev-btn.active.WARNING { background: rgba(245,158,11,0.15); border-color: rgba(245,158,11,0.3); color: #fbbf24; }
.sev-btn.active.ERROR   { background: rgba(239,68,68,0.15);  border-color: rgba(239,68,68,0.3);  color: #f87171; }
.sev-btn:hover          { background: rgba(255,255,255,0.08); color: #94a3b8; }

.sev-count {
  background: rgba(255,255,255,0.08);
  border-radius: 3px;
  padding: 0 4px;
  font-size: 0.6rem;
}

.sev-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sev-dot.INFO    { background: #34d399; }
.sev-dot.WARNING { background: #fbbf24; }
.sev-dot.ERROR   { background: #f87171; }

.toolbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  cursor: pointer;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  color: #64748b;
  font-family: inherit;
  transition: all 0.15s;
}
.toolbar-btn:hover { background: rgba(255,255,255,0.08); color: #94a3b8; }

/* ── Stats bar ───────────────────────────────────────────────── */
.stats-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 6px 14px;
  background: #1a2744;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.67rem;
  color: #64748b;
}

.stat-error { color: #f87171; }

/* ── Table ───────────────────────────────────────────────────── */
.logs-table {
  display: flex;
  flex-direction: column;
}

.logs-table-head {
  display: grid;
  grid-template-columns: 28px 90px 60px 1fr 60px 70px 24px;
  gap: 0;
  padding: 5px 14px;
  background: #0f172a;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  font-size: 0.6rem;
  font-weight: 700;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  align-items: center;
}

.logs-body {
  max-height: 400px;
  overflow-y: auto;
}

.logs-body::-webkit-scrollbar { width: 4px; }
.logs-body::-webkit-scrollbar-track { background: transparent; }
.logs-body::-webkit-scrollbar-thumb { background: #334155; border-radius: 2px; }

/* ── Log row ─────────────────────────────────────────────────── */
.log-row {
  width: 100%;
  display: grid;
  grid-template-columns: 28px 90px 60px 1fr 60px 70px 24px;
  gap: 0;
  padding: 5px 14px;
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(255,255,255,0.025);
  cursor: pointer;
  align-items: center;
  text-align: left;
  font-family: inherit;
  font-size: 0.72rem;
  transition: background 0.12s;
}
.log-row:hover { background: rgba(255,255,255,0.04); }
.log-row.row-expanded { background: rgba(255,255,255,0.03); }

.log-row.sev-error   { border-left: 2px solid #ef4444; }
.log-row.sev-warning { border-left: 2px solid #f59e0b; }
.log-row.sev-info    { border-left: 2px solid transparent; }
.log-row.sev-default { border-left: 2px solid transparent; }

/* Severity indicator dot */
.sev-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}
.sev-indicator.sev-error   { background: #ef4444; box-shadow: 0 0 4px rgba(239,68,68,0.5); }
.sev-indicator.sev-warning { background: #f59e0b; box-shadow: 0 0 4px rgba(245,158,11,0.5); }
.sev-indicator.sev-info    { background: #10b981; }
.sev-indicator.sev-default { background: #475569; }

/* Column widths & content */
.col-sev      { display: flex; align-items: center; }
.col-time     { color: #64748b; font-size: 0.68rem; white-space: nowrap; }
.col-method   { }
.col-endpoint { color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 8px; }
.col-status   { }
.col-duration { color: #64748b; white-space: nowrap; }
.col-expand   { display: flex; align-items: center; justify-content: flex-end; }

/* Message texte non-HTTP (logs d'init, messages libres, erreurs) */
.message-text {
  color: #7dd3fc;
  font-style: italic;
  font-size: 0.69rem;
}

/* Method badges */
.method-badge {
  display: inline-block;
  font-size: 0.58rem;
  font-weight: 800;
  padding: 1px 5px;
  border-radius: 3px;
  letter-spacing: 0.04em;
}
.method-get    { background: rgba(16,185,129,0.15); color: #34d399; }
.method-post   { background: rgba(59,130,246,0.15); color: #60a5fa; }
.method-put    { background: rgba(245,158,11,0.15); color: #fbbf24; }
.method-delete { background: rgba(239,68,68,0.15);  color: #f87171; }
.method-patch  { background: rgba(168,85,247,0.15); color: #c084fc; }
.method-other  { background: rgba(100,116,139,0.15); color: #94a3b8; }

/* Status badges */
.status-badge {
  display: inline-block;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
}
.status-2xx { background: rgba(16,185,129,0.12);  color: #34d399; }
.status-3xx { background: rgba(59,130,246,0.12);  color: #60a5fa; }
.status-4xx { background: rgba(245,158,11,0.12);  color: #fbbf24; }
.status-5xx { background: rgba(239,68,68,0.12);   color: #f87171; }

.status-empty { color: #334155; font-size: 0.68rem; }

.duration-val { color: #7dd3fc; }

/* Expand chevron */
.expand-chevron { color: #475569; transition: transform 0.15s; }
.expand-chevron.open { transform: rotate(180deg); }

/* ── Expanded detail ─────────────────────────────────────────── */
.log-slide-enter-active,
.log-slide-leave-active {
  transition: all 0.18s ease;
  overflow: hidden;
}
.log-slide-enter-from,
.log-slide-leave-to {
  max-height: 0;
  opacity: 0;
}
.log-slide-enter-to,
.log-slide-leave-from {
  max-height: 500px;
  opacity: 1;
}

.log-detail {
  padding: 10px 14px 12px 40px;
  background: rgba(255,255,255,0.02);
  border-bottom: 1px solid rgba(255,255,255,0.04);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 6px 16px;
  margin-bottom: 8px;
}

.detail-kv {
  display: flex;
  gap: 6px;
  align-items: baseline;
  font-size: 0.68rem;
  line-height: 1.4;
}

.detail-kv.full-width {
  grid-column: 1 / -1;
}

.detail-key {
  color: #64748b;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.detail-val {
  color: #94a3b8;
  word-break: break-all;
}

.copy-detail-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  cursor: pointer;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  color: #64748b;
  font-family: inherit;
  transition: all 0.15s;
}
.copy-detail-btn:hover { background: rgba(255,255,255,0.08); color: #94a3b8; }

/* ── Empty state ─────────────────────────────────────────────── */
.logs-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px 16px;
  color: #475569;
  font-size: 0.8rem;
  font-family: inherit;
}
</style>
