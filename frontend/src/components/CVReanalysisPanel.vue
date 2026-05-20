<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
// parsePaginated bypass (endpoints fetched here are not paginated: CV reanalysis status)
import { RefreshCw, Users, Tag, Search, AlertTriangle, CheckCircle2, Zap } from 'lucide-vue-next'
import { authService } from '../services/auth'

const router = useRouter()

const isLoading = ref(false)
const error = ref('')
const successMessage = ref('')
const logs = ref<string[]>([])

const filterType = ref<'user' | 'tag'>('user')
const filterTag = ref('')
const selectedUser = ref<any>(null)
const userSearchQuery = ref('')
const userResults = ref<any[]>([])
const isSearchingUsers = ref(false)

// Seule la ré-analyse d'un unique consultant est autorisée en temps réel.
// Pour "tous les CVs" ou "une agence entière", on redirige vers le Pipeline Vertex AI Batch.
const canRunRealtime = computed(() =>
  filterType.value === 'user' && selectedUser.value !== null
)

const searchUsers = async () => {
  if (userSearchQuery.value.length < 2) {
    userResults.value = []
    return
  }
  isSearchingUsers.value = true
  try {
    const resp = await axios.get('/api/users/search', { params: { query: userSearchQuery.value, limit: 10 } })
    userResults.value = resp.data.items || []
  } catch (e) {
    console.error('User search failed', e)
  } finally {
    isSearchingUsers.value = false
  }
}

const selectUser = (user: any) => {
  selectedUser.value = user
  userSearchQuery.value = user.full_name || user.username
  userResults.value = []
}

const addLog = (msg: string) => {
  logs.value.unshift(`[${new Date().toLocaleTimeString()}] ${msg}`)
}

const goToBulkImport = () => {
  router.push('/admin/bulk-import')
}

// Ré-analyse temps réel — uniquement pour un seul consultant.
const triggerReanalysis = async () => {
  if (!selectedUser.value) return
  if (!confirm(`Relancer l'analyse Gemini pour ${selectedUser.value.full_name || selectedUser.value.username} ?`)) return

  isLoading.value = true
  error.value = ''
  successMessage.value = ''
  logs.value = []
  addLog(`Démarrage de la réanalyse pour user_id=${selectedUser.value.id}...`)

  try {
    const params = new URLSearchParams()
    params.append('user_id', selectedUser.value.id)

    const response = await fetch(`/api/cv/reanalyze?${params.toString()}`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${authService.state.token}` }
    })

    if (!response.ok) {
      const d = await response.json()
      throw new Error(d.detail || 'Erreur')
    }

    const contentType = response.headers.get('content-type')
    if (contentType && contentType.includes('application/json')) {
      const data = await response.json()
      addLog(JSON.stringify(data, null, 4))
      return
    }

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()

    if (reader) {
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.trim()) continue
          try {
            const data = JSON.parse(line)
            if (data.status === 'completed') {
              successMessage.value = data.message
              addLog(`TERMINÉ: ${data.message}`)
              if (data.errors?.length) data.errors.forEach((err: string) => addLog(`ERREUR: ${err}`))
            } else {
              addLog(data.message)
            }
          } catch (e) {
            console.error(e)
          }
        }
      }
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e.message || 'Erreur'
    error.value = detail
    addLog(`ÉCHEC: ${error.value}`)
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="glass-panel">
    <div class="panel-header">
      <h3><RefreshCw size="20" /> Relancer l'Analyse IA</h3>
    </div>
    <div class="panel-content">

      <!-- Bannière d'information sur le batch -->
      <div class="batch-info-banner">
        <Zap size="16" />
        <div>
          <strong>Ré-analyse en masse = Pipeline Vertex AI Batch.</strong>
          Pour traiter plusieurs CVs (agence entière ou tous les consultants),
          utilisez le pipeline dédié qui garantit un coût réduit et aucune saturation.
          <button class="link-btn" @click="goToBulkImport">
            → Ouvrir le Pipeline Batch
          </button>
        </div>
      </div>

      <p class="section-desc">
        Ré-analyser le CV d'<strong>un seul consultant</strong> avec Gemini (utile si son CV a changé ou en cas d'erreur ponctuelle).
      </p>

      <div class="filter-controls">
        <label class="radio-label">
          <input type="radio" v-model="filterType" value="user" id="filter-user">
          <span>Un Consultant</span>
        </label>
        <label class="radio-label">
          <input type="radio" v-model="filterType" value="tag" id="filter-tag-radio">
          <span>Agence entière (→ Batch)</span>
        </label>
      </div>

      <!-- Sélection d'un seul utilisateur -->
      <div v-if="filterType === 'user'" class="input-group relative">
        <Search size="16" class="mt-3.5" />
        <input type="text" v-model="userSearchQuery" id="user-search-query" @input="searchUsers" placeholder="Chercher un utilisateur..." class="form-input">
        <div v-if="userResults.length > 0" class="autocomplete-dropdown">
          <div v-for="user in userResults" :key="user.id" @click="selectUser(user)" class="autocomplete-item">
            <span class="fw-bold">{{ user.full_name || user.username }}</span> ({{ user.email }})
          </div>
        </div>
        <div v-if="selectedUser" class="selected-user-badge">
          Sélection : <strong>{{ selectedUser.full_name || selectedUser.username }}</strong>
        </div>
      </div>

      <!-- Mode agence : redirection Batch uniquement -->
      <div v-if="filterType === 'tag'" class="batch-redirect-block">
        <div class="input-group">
          <Tag size="16" class="mt-3.5" />
          <input type="text" v-model="filterTag" id="filter-tag" placeholder="Nom de l'agence (ex: 'zenika-lyon')" class="form-input">
        </div>
        <p class="redirect-hint">
          ⚠️ L'analyse d'une agence entière traite potentiellement des centaines de CVs.
          Elle doit obligatoirement passer par le <strong>Pipeline Vertex AI Batch</strong>.
        </p>
        <button class="action-btn primary-btn" @click="goToBulkImport" aria-label="Ouvrir le Pipeline Batch">
          <Zap size="18" /> Ouvrir le Pipeline Batch
        </button>
      </div>

      <!-- Action temps réel (user seulement) -->
      <div v-if="filterType === 'user'" class="actions mt-4">
        <button
          class="action-btn warning-btn"
          @click="triggerReanalysis"
          :disabled="isLoading || !canRunRealtime"
          :title="!canRunRealtime ? 'Sélectionnez un consultant d\'abord' : 'Relancer l\'analyse pour ce consultant'"
        >
          <RefreshCw size="18" :class="{ 'spin': isLoading }" />
          {{ isLoading ? 'Réanalyse en cours...' : 'Relancer pour ce consultant' }}
        </button>
      </div>

      <div v-if="error" class="status-box error-box mt-4">
        <AlertTriangle size="20" /> <span>{{ error }}</span>
      </div>

      <div v-if="successMessage" class="status-box success-box mt-4">
        <CheckCircle2 size="20" /> <span>{{ successMessage }}</span>
      </div>

      <div class="logs-container mt-4" v-if="logs.length > 0">
          <h4>Journal d'Exécution</h4>
          <div class="terminal">
            <div v-for="(log, idx) in logs" :key="'log-' + idx" class="log-line" :class="{ 'text-red': log.includes('ERREUR') || log.includes('ÉCHEC') }">
              {{ log }}
            </div>
          </div>
        </div>
    </div>
  </div>
</template>

<style scoped>
.glass-panel {
  background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(24px); border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 16px; box-shadow: 0 12px 40px rgba(227, 25, 55, 0.08); overflow: hidden; margin-bottom: 2rem;
}
.panel-header { padding: 24px 30px; border-bottom: 1px solid rgba(0, 0, 0, 0.05); background: rgba(20, 20, 20, 0.02); }
.panel-header h3 { display: flex; align-items: center; gap: 10px; font-size: 1.1rem; color: #1a1a1a; margin: 0; font-weight: 600; }
.panel-content { padding: 30px; }
.section-desc { color: #64748b; font-size: 0.95rem; margin-bottom: 20px; line-height: 1.5; }

/* Bannière info Batch */
.batch-info-banner {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-left: 3px solid #6366f1;
  border-radius: 10px;
  padding: 14px 16px;
  font-size: 0.88rem;
  color: #312e81;
  margin-bottom: 20px;
  line-height: 1.5;
}
.batch-info-banner svg { color: #6366f1; flex-shrink: 0; margin-top: 2px; }
.link-btn {
  background: none; border: none; color: #6366f1; font-weight: 700; cursor: pointer;
  font-size: 0.88rem; padding: 0; text-decoration: underline;
}
.link-btn:hover { color: #4338ca; }

/* Redirection block */
.batch-redirect-block { display: flex; flex-direction: column; gap: 12px; }
.redirect-hint {
  background: rgba(245, 158, 11, 0.07);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 0.88rem;
  color: #92400e;
  line-height: 1.5;
}

.filter-controls { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
.radio-label { display: flex; align-items: center; gap: 8px; cursor: pointer; color: #334155; font-size: 0.95rem; }
.input-group { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
.form-input { flex: 1; padding: 12px 16px; border: 1px solid #e2e8f0; border-radius: 10px; font-size: 0.95rem; transition: all 0.2s; }
.form-input:focus { outline: none; border-color: #E31937; box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1); }
.autocomplete-dropdown { position: absolute; top: 100%; left: 28px; right: 0; background: white; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-height: 200px; overflow-y: auto; z-index: 10; margin-top: 4px; }
.autocomplete-item { padding: 10px 16px; cursor: pointer; border-bottom: 1px solid #f8fafc; font-size: 0.9rem; }
.autocomplete-item:hover { background: #f1f5f9; }
.selected-user-badge { background: #ecfdf5; color: #059669; padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; border: 1px solid #a7f3d0; margin-top: 8px; margin-left: 28px; }
.actions { display: flex; gap: 12px; }
.action-btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 12px 24px; border-radius: 10px; font-weight: 600; cursor: pointer; transition: all 0.2s; border: none; font-size: 0.95rem; }
.warning-btn { background: #f59e0b; color: white; }
.warning-btn:hover { background: #d97706; }
.warning-btn:disabled { opacity: 0.7; cursor: not-allowed; }
.primary-btn { background: #6366f1; color: white; }
.primary-btn:hover { background: #4f46e5; }
.status-box { display: flex; align-items: flex-start; gap: 12px; padding: 16px; border-radius: 10px; font-size: 0.95rem; font-weight: 500; }
.error-box { background: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }
.success-box { background: #ecfdf5; color: #059669; border: 1px solid #a7f3d0; }
.logs-container h4 { font-size: 0.9rem; color: #64748b; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; }
.terminal { background: #1e293b; color: #e2e8f0; font-family: monospace; font-size: 0.85rem; padding: 16px; border-radius: 10px; max-height: 250px; overflow-y: auto; }
.log-line { margin-bottom: 4px; line-height: 1.4; word-break: break-all; }
.text-red { color: #f87171; }
.spin { animation: spin 1s infinite linear; }
@keyframes spin { to { transform: rotate(360deg); } }
.mt-4 { margin-top: 1rem; }
.mt-3\.5 { margin-top: 0.875rem; }
.relative { position: relative; }
</style>
