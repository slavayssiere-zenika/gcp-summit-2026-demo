<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chatStore'
import { useUxStore } from '@/stores/uxStore'
import { authService } from '@/services/auth'
import axios from 'axios'
import {
  Bot, Network, Briefcase, Database, RefreshCw, CheckCircle2, AlertTriangle, Play
} from 'lucide-vue-next'

const router = useRouter()
const { t, locale } = useI18n()
const chatStore = useChatStore()
const uxStore = useUxStore()

const globalProgress = ref(0)
const logLines = ref<string[]>([])
const hasFailed = ref(false)
const isDegraded = ref(false)
const currentTipIndex = ref(0)
let tipsInterval: ReturnType<typeof setInterval> | null = null

const services = ref([
  { id: 'gateway', name: 'Gateway Orchestrator', status: 'pending', icon: Bot },
  { id: 'agents', name: 'Multi-Agent Engines (HR, Ops, Missions)', status: 'pending', icon: Network },
  { id: 'data', name: 'Competencies & Missions Data Layer', status: 'pending', icon: Briefcase },
  { id: 'history', name: 'Conversation History & Cache', status: 'pending', icon: Database },
])

const tips = [
  "L'Assistant s'appuie sur pgvector pour identifier des profils de consultants proches de vos besoins sans exiger une correspondance de mots-clés exacte.",
  "Le cache sémantique de l'agent router répond instantanément et à coût FinOps nul aux questions récurrentes déjà posées par l'équipe.",
  "Les sous-agents (HR, Ops, Missions) s'exécutent de manière asynchrone et découvrent leurs compétences dynamiquement grâce au protocole A2A v2.",
  "La consommation de tokens IA est mesurée et sauvegardée en temps réel dans BigQuery pour optimiser nos budgets d'inférence (FinOps)."
]

const addLog = (msg: string) => {
  logLines.value.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
  setTimeout(() => {
    const el = document.getElementById('log-terminal')
    if (el) el.scrollTop = el.scrollHeight
  }, 30)
}

const reportDegradedToSre = async (serviceName: string) => {
  try {
    const token = localStorage.getItem('access_token')
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    await axios.post('/api/warmup/degraded', { service: serviceName }, { headers, timeout: 3000 })
  } catch (e) {
    // Ignorer silencieusement pour éviter les boucles en cas de panne réseau complète
  }
}

const robustPing = async (url: string, serviceName: string, retries = 3, delay = 1500): Promise<boolean> => {
  const token = localStorage.getItem('access_token')
  const headers = token ? { Authorization: `Bearer ${token}` } : {}

  for (let i = 0; i < retries; i++) {
    try {
      addLog(t('warming.ping_attempt', { service: serviceName, current: i + 1, total: retries }) || `Ping ${serviceName} (tentative ${i + 1}/${retries})...`)
      const res = await axios.get(url, { headers, timeout: 5000 })
      if (res.status === 200) {
        addLog(`✓ ${serviceName} is hot and ready !`)
        return true
      }
    } catch (e: any) {
      addLog(`⚠ ${serviceName} starting up (status: ${e.response?.status || 'Timeout'})...`)
      if (i < retries - 1) {
        await new Promise(resolve => setTimeout(resolve, delay * (i + 1)))
      }
    }
  }

  // Notifier l'admin localement (uxStore) et globalement (SRE log)
  uxStore.addDegradedService(serviceName)
  await reportDegradedToSre(serviceName)
  return false
}

const runWarmingFlow = async () => {
  hasFailed.value = false
  isDegraded.value = false
  uxStore.clearDegradedServices()
  globalProgress.value = 5
  addLog(t('warming.starting_protocol') || "Lancement du protocole de Warm-up Zenika AI Console...")

  // Étape 1 : Router Gateway
  services.value[0].status = 'warming'
  const gatewayWarm = await robustPing('/api/health', 'Gateway Router', 3, 1000)
  if (!gatewayWarm) {
    services.value[0].status = 'failed'
    hasFailed.value = true
    addLog(t('warming.failed_gateway') || "❌ Échec critique : La Gateway Router ne répond pas.")
    return
  }
  services.value[0].status = 'ready'
  globalProgress.value = 25

  // Étape 2 : Agents
  services.value[1].status = 'warming'
  const agentsWarm = await robustPing('/api/health/agents', 'Sous-Agents (HR, Ops, Missions)', 3, 1500)
  if (!agentsWarm) {
    services.value[1].status = 'failed'
    hasFailed.value = true
    addLog(t('warming.failed_agents') || "❌ Échec critique : Les sous-agents IA n'ont pas pu démarrer.")
    return
  }
  services.value[1].status = 'ready'
  globalProgress.value = 50

  // Étape 3 : Data APIs (Competencies, Missions, CVs, etc.)
  services.value[2].status = 'warming'
  const [compWarm, missionWarm, cvWarm] = await Promise.all([
    robustPing('/api/competencies/health', 'Competencies API', 3, 1000),
    robustPing('/api/missions/health', 'Missions API', 3, 1000),
    robustPing('/api/cv/health', 'CV API', 3, 1000)
  ])

  if (!compWarm || !missionWarm || !cvWarm) {
    addLog(t('warming.degraded_mode') || "⚠ Certains services de données sont lents. Activation du mode dégradé.")
    isDegraded.value = true
    services.value[2].status = 'degraded'
  } else {
    services.value[2].status = 'ready'
  }
  globalProgress.value = 75

  // Étape 4 : History Preload & Sessions Cache
  services.value[3].status = 'warming'
  addLog(t('warming.hydrating_cache') || "Réhydratation du cache des sessions et de l'historique actif...")
  try {
    await chatStore.loadSessions()
    services.value[3].status = 'ready'
    addLog(t('warming.history_ready') || "✓ Historique de conversation pré-chargé avec succès !")
  } catch (err) {
    addLog(t('warming.history_failed') || "⚠ Impossible de pré-charger l'historique (mode dégradé).")
    services.value[3].status = 'degraded'
    isDegraded.value = true
  }
  globalProgress.value = 100

  // Finalisation et redirection
  addLog(t('warming.complete_redirect') || "Tout est prêt ! Initialisation de votre espace de travail...")
  setTimeout(() => {
    sessionStorage.setItem('zenika_warmed', 'true')
    router.push('/')
  }, 1000)
}

onMounted(() => {
  // Cycle tips every 3.5s
  tipsInterval = setInterval(() => {
    currentTipIndex.value = (currentTipIndex.value + 1) % tips.length
  }, 3500)

  runWarmingFlow()
})

onUnmounted(() => {
  if (tipsInterval) clearInterval(tipsInterval)
})
</script>

<template>
  <div class="warming-container">
    <div class="warming-card">
      <div class="warming-header">
        <div class="zenika-logo">ZENIKA</div>
        <h1>{{ t('warming.title') || 'Préparation de la console' }}</h1>
        <p>{{ t('warming.subtitle') || 'Veuillez patienter pendant le pré-chauffage des services Cloud Run.' }}</p>
      </div>

      <!-- Center Progress Ring -->
      <div class="progress-section">
        <div class="progress-ring-container">
          <svg class="progress-ring" width="160" height="160">
            <circle
              class="progress-ring-bg"
              stroke="#e2e8f0"
              stroke-width="8"
              fill="transparent"
              r="70"
              cx="80"
              cy="80"
            />
            <circle
              class="progress-ring-bar"
              stroke="var(--zenika-red)"
              stroke-width="8"
              fill="transparent"
              r="70"
              cx="80"
              cy="80"
              stroke-dasharray="439.8"
              :stroke-dashoffset="439.8 - (439.8 * globalProgress) / 100"
            />
          </svg>
          <div class="progress-text">
            <span class="progress-num">{{ globalProgress }}%</span>
            <span class="progress-label">{{ isDegraded ? 'Degraded' : 'Active' }}</span>
          </div>
        </div>
      </div>

      <!-- Services Grid Dashboard -->
      <div class="services-list">
        <div 
          v-for="s in services" 
          :key="s.id" 
          :class="['service-item', s.status]"
        >
          <component :is="s.icon" size="18" class="service-icon" />
          <span class="service-name">{{ s.name }}</span>
          <div class="service-status-badge">
            <span v-if="s.status === 'pending'" class="dot pending"></span>
            <span v-else-if="s.status === 'warming'" class="spinner"></span>
            <span v-else-if="s.status === 'ready'" class="badge ready">Ready</span>
            <span v-else-if="s.status === 'degraded'" class="badge degraded">Warm</span>
            <span v-else-if="s.status === 'failed'" class="badge failed">Failed</span>
          </div>
        </div>
      </div>

      <!-- Tips Box -->
      <div class="tips-box">
        <div class="tips-title">💡 {{ t('warming.tip_title') || 'Le saviez-vous ?' }}</div>
        <transition name="fade-slide" mode="out-in">
          <p :key="currentTipIndex" class="tips-body">{{ tips[currentTipIndex] }}</p>
        </transition>
      </div>

      <!-- Logs Terminal -->
      <div class="terminal-container">
        <div class="terminal-header">
          <span class="term-dot red"></span>
          <span class="term-dot yellow"></span>
          <span class="term-dot green"></span>
          <span class="term-title">sre-console-logs.sh</span>
        </div>
        <div class="terminal-body" id="log-terminal">
          <div v-for="(line, idx) in logLines" :key="idx" class="log-line">
            {{ line }}
          </div>
        </div>
      </div>

      <!-- Action Panel if failed -->
      <div v-if="hasFailed" class="failed-panel">
        <div class="error-msg">
          <AlertTriangle size="20" />
          <span>{{ t('warming.critical_error') || "Échec d'initialisation des services critiques." }}</span>
        </div>
        <button @click="runWarmingFlow" class="retry-btn">
          <RefreshCw size="16" />
          {{ t('warming.retry_btn') || 'Réessayer le démarrage' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.warming-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 120px);
  background: var(--bg-gradient);
  padding: 1rem;
}

.warming-card {
  background: #0f172a; /* Ultra premium dark charcoal background */
  color: #f8fafc;
  padding: 2.5rem;
  border-radius: 24px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  width: 100%;
  max-width: 580px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  animation: slideUp 0.6s cubic-bezier(0.23, 1, 0.32, 1);
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.warming-header {
  text-align: center;
  margin-bottom: 1.5rem;
}

.zenika-logo {
  font-weight: 900;
  font-size: 2rem;
  color: var(--zenika-red);
  letter-spacing: -1px;
  margin-bottom: 0.5rem;
  text-shadow: 0 0 20px rgba(227, 25, 55, 0.3);
}

h1 {
  font-size: 1.35rem;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 0.4rem;
}

p {
  color: #94a3b8;
  font-size: 0.9rem;
  line-height: 1.4;
}

.progress-section {
  display: flex;
  justify-content: center;
  margin-bottom: 2rem;
}

.progress-ring-container {
  position: relative;
  width: 160px;
  height: 160px;
}

.progress-ring-bar {
  transform: rotate(-90deg);
  transform-origin: 50% 50%;
  transition: stroke-dashoffset 0.35s ease;
}

.progress-text {
  position: absolute;
  top: 0;
  left: 0;
  width: 160px;
  height: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.progress-num {
  font-size: 2rem;
  font-weight: 800;
  color: #ffffff;
}

.progress-label {
  font-size: 0.72rem;
  color: #64748b;
  text-transform: uppercase;
  font-weight: 700;
  letter-spacing: 0.05em;
  margin-top: 2px;
}

.services-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin-bottom: 1.5rem;
}

.service-item {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.04);
  transition: all 0.3s;
}

.service-item.ready {
  background: rgba(16, 185, 129, 0.06);
  border-color: rgba(16, 185, 129, 0.15);
}

.service-item.degraded {
  background: rgba(245, 158, 11, 0.06);
  border-color: rgba(245, 158, 11, 0.15);
}

.service-item.failed {
  background: rgba(239, 68, 68, 0.06);
  border-color: rgba(239, 68, 68, 0.15);
}

.service-icon {
  color: #64748b;
  margin-right: 0.75rem;
  transition: color 0.3s;
}

.ready .service-icon { color: #10b981; }
.degraded .service-icon { color: #f59e0b; }
.failed .service-icon { color: #ef4444; }

.service-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: #cbd5e1;
}

.service-status-badge {
  margin-left: auto;
  display: flex;
  align-items: center;
}

.dot.pending {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #475569;
  display: inline-block;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 50%;
  border-top-color: var(--zenika-red);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.badge {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  text-transform: uppercase;
}

.badge.ready {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
}

.badge.degraded {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
}

.badge.failed {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}

/* Tips Box Styling */
.tips-box {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
  min-height: 90px;
}

.tips-title {
  font-size: 0.75rem;
  font-weight: 700;
  color: #38bdf8;
  margin-bottom: 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tips-body {
  font-size: 0.8rem;
  color: #94a3b8;
  line-height: 1.45;
}

/* Fade Slide transition for Tips */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateX(10px);
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}

/* Terminal Container Styling */
.terminal-container {
  background: #020617;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  font-family: monospace;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #0f172a;
  padding: 0.4rem 0.8rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.term-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
}

.term-dot.red { background: #ef4444; }
.term-dot.yellow { background: #f59e0b; }
.term-dot.green { background: #10b981; }

.term-title {
  font-size: 0.68rem;
  color: #475569;
  margin-left: 0.5rem;
}

.terminal-body {
  padding: 0.75rem;
  height: 100px;
  overflow-y: auto;
  font-size: 0.72rem;
  color: #38bdf8; /* cyber blue log color */
  line-height: 1.4;
  scroll-behavior: smooth;
}

/* Custom scrollbar for terminal */
.terminal-body::-webkit-scrollbar {
  width: 4px;
}
.terminal-body::-webkit-scrollbar-track {
  background: transparent;
}
.terminal-body::-webkit-scrollbar-thumb {
  background: #1e293b;
  border-radius: 2px;
}

.log-line {
  white-space: pre-wrap;
  word-break: break-all;
  margin-bottom: 2px;
}

/* Failed panel styling */
.failed-panel {
  margin-top: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  animation: shake 0.4s linear;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-5px); }
  75% { transform: translateX(5px); }
}

.error-msg {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  padding: 0.75rem 1rem;
  border-radius: 12px;
  color: #f87171;
  font-size: 0.82rem;
  font-weight: 600;
}

.retry-btn {
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 0.8rem;
  border-radius: 12px;
  font-weight: 700;
  font-size: 0.88rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.25);
}

.retry-btn:hover {
  background: #c81530;
  transform: translateY(-1px);
}
</style>
