<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import markdownit from 'markdown-it'
import {
  BookOpen, AlertCircle, RefreshCw, GitBranch,
  Users, Briefcase, Activity, CheckCircle2, XCircle, Loader2
} from 'lucide-vue-next'

const md = markdownit({ html: true, linkify: true, typographer: true })

interface AgentTab {
  id: string
  name: string
  role: string
  specUrl: string
  versionUrl: string
  healthUrl: string
  icon: any
  color: string
}

const agents: AgentTab[] = [
  {
    id: 'router',
    name: 'Router',
    role: 'Orchestrateur Front-Desk',
    specUrl: '/api/spec',
    versionUrl: '/api/version',
    healthUrl: '/api/health',
    icon: GitBranch,
    color: '#E31937'
  },
  {
    id: 'hr',
    name: 'Agent HR',
    role: 'Talent & Compétences',
    specUrl: '/api/agent-hr/spec',
    versionUrl: '/api/agent-hr/version',
    healthUrl: '/api/agent-hr/health',
    icon: Users,
    color: '#7C3AED'
  },
  {
    id: 'missions',
    name: 'Agent Missions',
    role: 'Staffing Director',
    specUrl: '/api/agent-missions/spec',
    versionUrl: '/api/agent-missions/version',
    healthUrl: '/api/agent-missions/health',
    icon: Briefcase,
    color: '#2563EB'
  },
  {
    id: 'ops',
    name: 'Agent Ops',
    role: 'Monitoring & FinOps',
    specUrl: '/api/agent-ops/spec',
    versionUrl: '/api/agent-ops/version',
    healthUrl: '/api/agent-ops/health',
    icon: Activity,
    color: '#059669'
  }
]

type HealthStatus = 'ok' | 'error' | 'loading'

const versions = ref<Record<string, string>>({})
const healthStatuses = ref<Record<string, HealthStatus>>({})
const activeAgentId = ref(agents[0].id)
const activeAgent = computed(() => agents.find(a => a.id === activeAgentId.value) || agents[0])
const content = ref('')
const loading = ref(false)
const error = ref('')

const fetchAllMeta = async () => {
  agents.forEach(async (agent) => {
    healthStatuses.value[agent.id] = 'loading'

    // Version
    try {
      const vRes = await axios.get(agent.versionUrl, { validateStatus: () => true })
      versions.value[agent.id] = vRes.data?.version ?? vRes.data?.app_version ?? '??'
    } catch {
      versions.value[agent.id] = '??'
    }

    // Health — on vérifie le code HTTP (2xx = OK).
    // validateStatus : () => true évite qu'axios lève une exception sur 401/404,
    // ce qui permet de distinguer "service down" (erreur réseau) de "endpoint protégé".
    try {
      const hRes = await axios.get(agent.healthUrl, {
        validateStatus: () => true,
        timeout: 5000,
      })
      const httpOk = hRes.status >= 200 && hRes.status < 300
      const bodyOk = hRes.data?.status === 'ok' || hRes.data?.healthy === true
      healthStatuses.value[agent.id] = (httpOk || bodyOk) ? 'ok' : 'error'
    } catch (err) {
      console.warn(`[AgentsDocs] Health check failed for ${agent.id}:`, err)
      healthStatuses.value[agent.id] = 'error'
    }
  })
}

const fetchSpec = async () => {
  loading.value = true
  error.value = ''
  content.value = ''
  try {
    const res = await axios.get(activeAgent.value.specUrl)
    content.value = md.render(res.data)
  } catch {
    error.value = `Spécification indisponible — impossible de contacter ${activeAgent.value.name}.`
  } finally {
    loading.value = false
  }
}

const selectAgent = (id: string) => {
  activeAgentId.value = id
  fetchSpec()
}

onMounted(() => {
  fetchSpec()
  fetchAllMeta()
})
</script>

<template>
  <div class="agents-docs fade-in">
    <!-- Header -->
    <div class="header-section">
      <div class="title-wrapper">
        <BookOpen class="icon-title" :size="32" />
        <h2>Documentation des Agents IA</h2>
      </div>
      <p class="subtitle">Architecture & spécifications métier des agents intelligents Zenika</p>
    </div>

    <!-- Agent Cards selector -->
    <div class="agents-grid">
      <button
        v-for="agent in agents"
        :key="agent.id"
        class="agent-card"
        :class="{ active: activeAgentId === agent.id }"
        :style="activeAgentId === agent.id ? { '--accent': agent.color, borderColor: agent.color } : {}"
        @click="selectAgent(agent.id)"
        :aria-label="`Voir la documentation de ${agent.name}`"
      >
        <div class="agent-card-icon" :style="{ background: `${agent.color}18`, color: agent.color }">
          <component :is="agent.icon" :size="22" />
        </div>
        <div class="agent-card-body">
          <div class="agent-card-name">{{ agent.name }}</div>
          <div class="agent-card-role">{{ agent.role }}</div>
        </div>
        <div class="agent-card-meta">
          <span class="version-chip" v-if="versions[agent.id]">{{ versions[agent.id] }}</span>
          <span
            class="health-chip"
            :class="healthStatuses[agent.id]"
            :title="`Statut : ${healthStatuses[agent.id]}`"
          >
            <Loader2 v-if="healthStatuses[agent.id] === 'loading'" :size="12" class="spin" />
            <CheckCircle2 v-else-if="healthStatuses[agent.id] === 'ok'" :size="12" />
            <XCircle v-else :size="12" />
            <span>{{ healthStatuses[agent.id] === 'ok' ? 'OK' : healthStatuses[agent.id] === 'loading' ? '…' : 'KO' }}</span>
          </span>
        </div>
      </button>
    </div>

    <!-- Spec Reader -->
    <div class="reader-card glass-panel">
      <div class="card-header" :style="{ borderTopColor: activeAgent.color }">
        <div class="card-title">
          <component :is="activeAgent.icon" :size="20" class="mini-icon" :style="{ color: activeAgent.color }" />
          <h3>{{ activeAgent.name }} — {{ activeAgent.role }}</h3>
          <span v-if="versions[activeAgentId]" class="badge" :style="{ background: `${activeAgent.color}18`, color: activeAgent.color }">
            v{{ versions[activeAgentId] }}
          </span>
        </div>
        <button class="icon-btn" @click="fetchSpec" :disabled="loading" title="Actualiser">
          <RefreshCw :size="18" :class="{ spin: loading }" />
        </button>
      </div>

      <div class="reader-body">
        <div v-if="loading" class="state-center">
          <div class="spinner" :style="{ borderTopColor: activeAgent.color }"></div>
          <span>Chargement de la spécification...</span>
        </div>
        <div v-else-if="error" class="state-center error-state">
          <AlertCircle :size="48" class="err-icon" />
          <p>{{ error }}</p>
          <button class="retry-btn" @click="fetchSpec">Réessayer</button>
        </div>
        <div v-else class="markdown-content" v-html="content"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agents-docs {
  max-width: 1100px;
  margin: 0 auto;
  padding: 40px 20px;
}

/* Header */
.header-section {
  text-align: center;
  margin-bottom: 32px;
}
.title-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-bottom: 10px;
}
h2 {
  font-size: 34px;
  font-weight: 800;
  color: #1A1A1A;
  letter-spacing: -1px;
}
.icon-title { color: #E31937; }
.subtitle { color: #666; font-size: 17px; }

/* Agent Grid */
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 14px;
  margin-bottom: 28px;
}

.agent-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  background: rgba(255,255,255,0.6);
  border: 2px solid rgba(255,255,255,0.8);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  backdrop-filter: blur(14px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.05);
  text-align: left;
}
.agent-card:hover {
  transform: translateY(-3px);
  background: rgba(255,255,255,0.95);
  box-shadow: 0 8px 24px rgba(0,0,0,0.1);
}
.agent-card.active {
  border-color: var(--accent, #E31937);
  background: rgba(255,255,255,0.98);
  box-shadow: 0 6px 20px rgba(0,0,0,0.08);
}

.agent-card-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.agent-card-body { flex: 1; min-width: 0; }
.agent-card-name { font-size: 15px; font-weight: 700; color: #1A1A1A; }
.agent-card-role { font-size: 12px; color: #888; margin-top: 2px; }

.agent-card-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-end;
}

.version-chip {
  font-size: 11px;
  font-weight: 700;
  color: #888;
  background: rgba(0,0,0,0.04);
  padding: 2px 8px;
  border-radius: 20px;
  white-space: nowrap;
}

.health-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 20px;
}
.health-chip.ok { background: #d1fae5; color: #065f46; }
.health-chip.error { background: #fee2e2; color: #991b1b; }
.health-chip.loading { background: #f3f4f6; color: #6b7280; }

/* Reader Card */
.glass-panel {
  background: rgba(255,255,255,0.96);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255,255,255,0.7);
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.07);
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 28px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  background: rgba(250,250,250,0.95);
  border-top: 3px solid #E31937;
}
.card-title { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.mini-icon { flex-shrink: 0; }
h3 { font-size: 18px; font-weight: 700; color: #1A1A1A; margin: 0; }

.badge {
  font-size: 12px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 20px;
}

.icon-btn {
  background: transparent;
  border: 1px solid #e5e7eb;
  color: #6b7280;
  width: 36px; height: 36px;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}
.icon-btn:hover:not(:disabled) { background: #f3f4f6; color: #111; }

/* Reader body */
.reader-body { padding: 36px 40px; min-height: 380px; }

/* Markdown styles */
.markdown-content {
  color: #1A1A1A;
  line-height: 1.75;
  font-size: 16px;
}
.markdown-content :deep(h1) {
  font-size: 26px; font-weight: 800; color: #111;
  border-bottom: 2px solid rgba(227,25,55,0.2);
  padding-bottom: 8px; margin: 0 0 20px;
}
.markdown-content :deep(h2) { font-size: 20px; font-weight: 700; margin: 28px 0 12px; }
.markdown-content :deep(h3) { font-size: 16px; font-weight: 700; color: #444; margin: 20px 0 8px; }
.markdown-content :deep(code) {
  background: rgba(0,0,0,0.05); padding: 2px 7px;
  border-radius: 4px; font-family: monospace; font-size: 14px; color: #d32f2f;
}
.markdown-content :deep(pre) {
  background: #1e1e2e; padding: 20px; border-radius: 10px;
  overflow-x: auto; margin: 18px 0;
}
.markdown-content :deep(pre code) { background: transparent; color: #cdd6f4; font-size: 14px; }
.markdown-content :deep(blockquote) {
  border-left: 4px solid #E31937; margin: 0;
  padding: 12px 16px; background: rgba(227,25,55,0.03);
  border-radius: 0 8px 8px 0; color: #555;
}
.markdown-content :deep(table) { width: 100%; border-collapse: collapse; margin: 16px 0; }
.markdown-content :deep(th) {
  background: rgba(227,25,55,0.07); padding: 10px 14px;
  text-align: left; font-weight: 700; border-bottom: 2px solid rgba(0,0,0,0.08);
}
.markdown-content :deep(td) {
  padding: 10px 14px; border-bottom: 1px solid rgba(0,0,0,0.06);
}
.markdown-content :deep(tr:hover td) { background: rgba(0,0,0,0.02); }

/* States */
.state-center {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  text-align: center; padding: 70px 0; color: #777;
}
.error-state .err-icon { color: #E31937; margin-bottom: 16px; }
.retry-btn {
  margin-top: 18px; padding: 10px 24px;
  background: #E31937; color: #fff;
  border: none; font-weight: 600;
  border-radius: 8px; cursor: pointer;
  transition: background 0.2s;
}
.retry-btn:hover { background: #c2132e; }

/* Spinner */
.spinner {
  width: 40px; height: 40px;
  border: 3px solid rgba(227,25,55,0.15);
  border-top-color: #E31937;
  border-radius: 50%;
  animation: spin 0.9s infinite linear;
  margin-bottom: 18px;
}
.spin { animation: spin 0.9s infinite linear; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Fade in */
.fade-in { animation: fadeIn 0.35s ease-out; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Responsive */
@media (max-width: 768px) {
  .agents-grid { grid-template-columns: 1fr 1fr; }
  .reader-body { padding: 24px 20px; }
  h2 { font-size: 24px; }
}
</style>
