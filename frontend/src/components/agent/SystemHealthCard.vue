<script setup lang="ts">
import { computed } from 'vue'
import {
  CheckCircle2, XCircle, AlertTriangle, HelpCircle,
  Database, Server, Cpu, Activity, Wifi, WifiOff, RefreshCw
} from 'lucide-vue-next'

const props = defineProps<{
  components: {
    status: string
    component: string
    message?: string
    error?: string
    url?: string
    code?: number
  }[]
}>()

const summary = computed(() => {
  const total = props.components.length
  const healthy = props.components.filter(c => c.status === 'healthy').length
  const degraded = props.components.filter(c => c.status === 'degraded').length
  const unhealthy = props.components.filter(c => ['unhealthy', 'unreachable', 'error', 'not_found'].includes(c.status)).length
  return { total, healthy, degraded, unhealthy }
})

const overallStatus = computed(() => {
  if (summary.value.unhealthy > 0) return 'critical'
  if (summary.value.degraded > 0) return 'degraded'
  return 'healthy'
})

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'healthy': return CheckCircle2
    case 'degraded': return AlertTriangle
    case 'unreachable': return WifiOff
    case 'not_found': return HelpCircle
    default: return XCircle
  }
}

const getComponentIcon = (name: string) => {
  const n = name.toLowerCase()
  if (n.includes('redis')) return Database
  if (n.includes('bigquery') || n.includes('alloydb') || n.includes('db')) return Database
  if (n.includes('agent') || n.includes('router')) return Cpu
  if (n.includes('mcp') || n.includes('market')) return Activity
  return Server
}

const getStatusColor = (status: string) => {
  switch (status) {
    case 'healthy': return 'healthy'
    case 'degraded': return 'degraded'
    case 'unknown': return 'unknown'
    default: return 'critical'
  }
}

const formatComponentName = (name: string) => {
  return name
    .replace(/-dev$/, '')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}
</script>

<template>
  <div class="system-health-wrapper">
    <!-- Global Status Banner -->
    <div class="global-status" :class="overallStatus">
      <div class="global-status-left">
        <div class="status-pulse" :class="overallStatus"></div>
        <div>
          <div class="global-title">
            <CheckCircle2 v-if="overallStatus === 'healthy'" size="20" />
            <AlertTriangle v-else-if="overallStatus === 'degraded'" size="20" />
            <XCircle v-else size="20" />
            <span>
              {{ overallStatus === 'healthy' ? 'Tous les systèmes sont opérationnels' :
                 overallStatus === 'degraded' ? 'Dégradation détectée' :
                 'Incident critique en cours' }}
            </span>
          </div>
          <div class="global-subtitle">
            {{ summary.total }} composants vérifiés
          </div>
        </div>
      </div>
      <div class="summary-chips">
        <span class="chip chip-healthy">
          <CheckCircle2 size="12" /> {{ summary.healthy }} OK
        </span>
        <span v-if="summary.degraded > 0" class="chip chip-degraded">
          <AlertTriangle size="12" /> {{ summary.degraded }} dégradé
        </span>
        <span v-if="summary.unhealthy > 0" class="chip chip-critical">
          <XCircle size="12" /> {{ summary.unhealthy }} KO
        </span>
      </div>
    </div>

    <!-- Component Grid -->
    <div class="components-grid">
      <div
        v-for="(comp, idx) in components"
        :key="idx"
        class="component-card"
        :class="getStatusColor(comp.status)"
      >
        <div class="comp-header">
          <div class="comp-icon-wrapper" :class="getStatusColor(comp.status)">
            <component :is="getComponentIcon(comp.component)" size="16" />
          </div>
          <div class="comp-name">{{ formatComponentName(comp.component) }}</div>
          <div class="comp-status-badge" :class="getStatusColor(comp.status)">
            <component :is="getStatusIcon(comp.status)" size="11" />
            {{ comp.status }}
          </div>
        </div>

        <div class="comp-detail">
          <span v-if="comp.message">{{ comp.message }}</span>
          <span v-else-if="comp.error" class="error-text">{{ comp.error }}</span>
          <span v-else-if="comp.url" class="url-text">
            <Wifi size="11" /> {{ comp.url }}
            <span v-if="comp.code" class="code-badge">{{ comp.code }}</span>
          </span>
          <span v-else class="unknown-text">Aucun détail disponible</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.system-health-wrapper {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* ── Global Status Banner ── */
.global-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-radius: 14px;
  gap: 1rem;
  flex-wrap: wrap;
  border: 1.5px solid transparent;
  transition: all 0.3s;
}

.global-status.healthy {
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
  border-color: #86efac;
}

.global-status.degraded {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-color: #fcd34d;
}

.global-status.critical {
  background: linear-gradient(135deg, #fff5f5 0%, #fee2e2 100%);
  border-color: #fca5a5;
}

.global-status-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-pulse {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
  position: relative;
}

.status-pulse.healthy {
  background: #10b981;
  box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4);
  animation: pulse-green 2s infinite;
}

.status-pulse.degraded {
  background: #f59e0b;
  animation: none;
}

.status-pulse.critical {
  background: #ef4444;
  animation: pulse-red 1s infinite;
}

@keyframes pulse-green {
  0%   { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
  70%  { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
  100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

@keyframes pulse-red {
  0%   { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.5); }
  70%  { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
  100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
}

.global-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 0.95rem;
  font-weight: 700;
  color: #1e293b;
}

.global-status.healthy .global-title { color: #14532d; }
.global-status.degraded .global-title { color: #78350f; }
.global-status.critical .global-title { color: #7f1d1d; }

.global-subtitle {
  font-size: 0.75rem;
  margin-top: 2px;
  color: #64748b;
  font-weight: 500;
}

.summary-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 0.72rem;
  font-weight: 700;
}

.chip-healthy  { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
.chip-degraded { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }
.chip-critical { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }

/* ── Components Grid ── */
.components-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 0.75rem;
}

.component-card {
  background: white;
  border-radius: 12px;
  padding: 0.85rem 1rem;
  border: 1.5px solid #e2e8f0;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.component-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.06);
}

.component-card.healthy  { border-left: 3px solid #10b981; }
.component-card.degraded { border-left: 3px solid #f59e0b; }
.component-card.critical { border-left: 3px solid #ef4444; }
.component-card.unknown  { border-left: 3px solid #94a3b8; }

.comp-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.comp-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  flex-shrink: 0;
}

.comp-icon-wrapper.healthy  { background: #dcfce7; color: #15803d; }
.comp-icon-wrapper.degraded { background: #fef3c7; color: #92400e; }
.comp-icon-wrapper.critical { background: #fee2e2; color: #991b1b; }
.comp-icon-wrapper.unknown  { background: #f1f5f9; color: #64748b; }

.comp-name {
  flex: 1;
  font-size: 0.82rem;
  font-weight: 700;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.comp-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: 99px;
  font-size: 0.67rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}

.comp-status-badge.healthy  { background: #dcfce7; color: #15803d; }
.comp-status-badge.degraded { background: #fef3c7; color: #92400e; }
.comp-status-badge.critical { background: #fee2e2; color: #991b1b; }
.comp-status-badge.unknown  { background: #f1f5f9; color: #64748b; }

.comp-detail {
  font-size: 0.75rem;
  color: #64748b;
  line-height: 1.4;
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}

.error-text { color: #dc2626; font-style: italic; }
.url-text   { display: flex; align-items: center; gap: 4px; color: #475569; font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; }
.unknown-text { color: #94a3b8; font-style: italic; }

.code-badge {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 0 5px;
  font-size: 0.65rem;
  font-weight: 700;
  color: #334155;
}
</style>
