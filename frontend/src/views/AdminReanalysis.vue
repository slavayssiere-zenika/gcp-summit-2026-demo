<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { 
  RefreshCw, 
  Users, 
  Tag, 
  Search, 
  AlertTriangle, 
  CheckCircle2, 
  Network,
  ShieldCheck,
  ChevronDown,
  Unlock
} from 'lucide-vue-next'
import { authService } from '../services/auth'

const isLoading = ref(false)
const error = ref('')
const successMessage = ref('')
const logs = ref<string[]>([])

const filterType = ref<'all' | 'tag' | 'user'>('all')
const filterTag = ref('')
const selectedUser = ref<any>(null)
const userSearchQuery = ref('')
const userResults = ref<any[]>([])
const isSearchingUsers = ref(false)
const logContainer = ref<HTMLElement | null>(null)

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

const triggerReanalysis = async () => {
  if (!confirm("Cette opération va EFFACER les compétences assignées aux utilisateurs ciblés et relancer l'analyse Gemini. Êtes-vous certain ?")) {
    return
  }

  isLoading.value = true
  error.value = ''
  successMessage.value = ''
  logs.value = []
  addLog("Démarrage du processus de réanalyse...")

  try {
    const params = new URLSearchParams()
    if (filterType.value === 'tag' && filterTag.value) {
      params.append('tag', filterTag.value)
      addLog(`Filtre appliqué : Tag = ${filterTag.value}`)
    } else if (filterType.value === 'user' && selectedUser.value) {
      params.append('user_id', selectedUser.value.id)
      addLog(`Filtre appliqué : Utilisateur = ${selectedUser.value.username}`)
    } else {
      addLog("Filtre appliqué : TOUS LES CVS")
    }

    const response = await fetch(`/api/cv/reanalyze?${params.toString()}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authService.state.token}`
      }
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.detail || 'Erreur lors de la réanalyse')
    }

    const contentType = response.headers.get("content-type")
    if (contentType && contentType.includes("application/json")) {
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
        buffer = lines.pop() || '' // Keep the last partial line in buffer

        for (const line of lines) {
          if (!line.trim()) continue
          try {
            const data = JSON.parse(line)
            if (data.status === 'completed') {
              successMessage.value = data.message
              addLog(`TERMINÉ: ${data.message}`)
              if (data.errors && data.errors.length > 0) {
                data.errors.forEach((err: string) => addLog(`ERREUR: ${err}`))
              }
            } else {
              addLog(data.message)
            }
          } catch (e) {
            console.error('Failed to parse log line', line, e)
          }
        }
      }
    }
  } catch (e: any) {
    const errData = e?.response?.data || {}
    const detail = errData?.detail || e.message || 'Erreur lors de la réanalyse'
    // Détection du verrou zombie
    if (detail.includes('déjà en cours') || detail.includes('already running')) {
      error.value = detail + ' Utilisez le bouton "Écraser le verrou" si aucune opération n\'est réellement active.'
    } else {
      error.value = detail
    }
    addLog(`ÉCHEC CRITIQUE: ${error.value}`)
  } finally {
    isLoading.value = false
  }
}

const resetReanalysisLock = async () => {
  if (!confirm('Forcer la réinitialisation du verrou de réanalyse ? À utiliser uniquement si une tâche est bloquée sans raison.')) return
  try {
    await axios.delete('/api/cv/reanalyze/reset')
    isLoading.value = false
    error.value = ''
    addLog('✅ Verrou réinitialisé. Vous pouvez relancer une réanalyse.')
  } catch (e: any) {
    addLog(`Erreur reset verrou: ${e?.response?.data?.detail || e.message}`)
  }
}

// Reuse logic from Admin.vue for tree recalculation
const isTreeLoading = ref(false)
const treeResult = ref<any>(null)
const treeCost = ref<number | null>(null)
const treePollingInterval = ref<any>(null)

const triggerRemapping = async () => {
  if (confirm("Générer la nouvelle taxonomie écrasera votre affichage actuel. Êtes-vous sûr ?")) {
    isTreeLoading.value = true
    error.value = ''
    treeResult.value = null
    treeCost.value = null
    addLog("Lancement du calcul de la nouvelle taxonomie via Gemini...")
    
    try {
      await axios.post('/api/cv/recalculate_tree')
      checkTreeTaskStatus()
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || "Erreur lors du lancement du calcul de l'arbre"
      addLog(`ERREUR arbre: ${error.value}`)
      isTreeLoading.value = false
    }
  }
}

const checkTreeTaskStatus = async () => {
  try {
    const resp = await axios.get('/api/cv/recalculate_tree/status')
    const data = resp.data
    
    if (data.status === 'running') {
      isTreeLoading.value = true
      treeResult.value = null
      
      if (data.logs && data.logs.length > 0) {
          const latestLog = data.logs[data.logs.length - 1]
          const msg = latestLog.includes('] ') ? latestLog.split('] ')[1] : latestLog
          if (logs.value.length === 0 || !logs.value[0].includes(msg)) {
              addLog(msg)
          }
      }
      
      if (!treePollingInterval.value) {
        treePollingInterval.value = setInterval(checkTreeTaskStatus, 3000)
      }
    } else {
      isTreeLoading.value = false
      if (treePollingInterval.value) {
        clearInterval(treePollingInterval.value)
        treePollingInterval.value = null
      }
      
      if (data.status === 'completed' && data.tree) {
        treeResult.value = data.tree
        treeCost.value = data.usage?.estimated_cost_usd || null
        if (!successMessage.value.includes('Taxonomie')) {
            successMessage.value = "Nouvelle taxonomie générée avec succès."
            addLog("Nouvelle taxonomie générée avec succès.")
        }
      } else if (data.status === 'error') {
        error.value = data.error || "Erreur lors du calcul de l'arbre"
        addLog(`ERREUR arbre: ${error.value}`)
      }
    }
  } catch (e) {
    console.error('Failed to check tree task status', e)
  }
}

const applyTree = async () => {
  isTreeLoading.value = true
  error.value = ''
  
  try {
    addLog("Sauvegarde de la taxonomie en base de données...")
    await axios.post('/api/competencies/bulk_tree', { tree: treeResult.value })
    addLog("Taxonomie appliquée et caches vidés.")
    treeResult.value = null
    successMessage.value = "Taxonomie officiellement mise à jour sur toute la plateforme."
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || "Erreur de synchro DB"
    addLog(`ERREUR sauvegarde: ${error.value}`)
  } finally {
    isTreeLoading.value = false
  }
}

const pollingInterval = ref<any>(null)

const checkTaskStatus = async () => {
  try {
    const resp = await axios.get('/api/cv/reanalyze/status')
    const data = resp.data
    
    if (data.status === 'running') {
      isLoading.value = true
      logs.value = [...(data.logs || [])].reverse() // Invert for display
      if (!pollingInterval.value) {
        pollingInterval.value = setInterval(checkTaskStatus, 3000)
      }
    } else {
      isLoading.value = false
      if (pollingInterval.value) {
        clearInterval(pollingInterval.value)
        pollingInterval.value = null
      }
      if (data.status === 'completed') {
        logs.value = [...(data.logs || [])].reverse()
        // If it was running and now it's done, show success
        if (isLoading.value) {
            successMessage.value = data.message
        }
      }
    }
  } catch (e) {
    console.error('Failed to check task status', e)
  }
}

onMounted(() => {
  checkTaskStatus()
  checkTreeTaskStatus()
})
onUnmounted(() => {
  if (pollingInterval.value) {
    clearInterval(pollingInterval.value)
  }
  if (treePollingInterval.value) {
    clearInterval(treePollingInterval.value)
  }
})
</script>

<template>
  <div class="reanalysis-wrapper fade-in">
    <div class="header-banner">
      <div class="banner-icon"><RefreshCw size="32" /></div>
      <div class="banner-text">
        <h2>Réanalyse Globale & IA Taxonomy</h2>
        <p>Pilotez la mise à jour massive des profils consultants et structurez vos compétences.</p>
      </div>
      <div class="status-badge" v-if="authService.state.user?.role === 'admin'">
        <ShieldCheck size="16" /> Admin Control
      </div>
    </div>

    <div class="dashboard-grid">
      <!-- Section 1: Recalcul de l'Arbre -->
      <div class="glass-panel tree-panel">
        <div class="panel-header">
          <h3><Network size="20" /> Taxonomie & Structure</h3>
        </div>
        <div class="panel-content">
          <p class="section-desc">Générez une nouvelle structure de compétences (Taxonomie) basée sur l'ensemble des données actuelles via Gemini.</p>
          <div class="actions">
            <button 
              class="action-btn secondary-btn" 
              @click="triggerRemapping"
              :disabled="isLoading || isTreeLoading"
            >
              <Network size="20" :class="{ 'pulse-animation': isTreeLoading }" />
              {{ isTreeLoading ? 'Calcul en cours...' : "Recalculer l'Arbre" }}
            </button>
          </div>
        </div>
      </div>

      <!-- Section 2: Réanalyse des CVs -->
      <div class="glass-panel cv-panel">
        <div class="panel-header">
          <h3><RefreshCw size="20" /> Réanalyse des Profils</h3>
        </div>
        
        <div class="filter-controls">
          <div class="control-group">
            <label>Portée de la réanalyse</label>
            <div class="filter-pills">
              <button 
                :class="{ active: filterType === 'all' }" 
                @click="filterType = 'all'"
              >Tous les CVs</button>
              <button 
                :class="{ active: filterType === 'tag' }" 
                @click="filterType = 'tag'"
              >Par Tag</button>
              <button 
                :class="{ active: filterType === 'user' }" 
                @click="filterType = 'user'"
              >Par Utilisateur</button>
            </div>
          </div>

          <div v-if="filterType === 'tag'" class="control-group fade-in">
            <label>Saisir le Tag (ex: 'Niort')</label>
            <div class="input-with-icon">
              <Tag size="18" />
              <input type="text" v-model="filterTag" placeholder="Nom du tag...">
            </div>
          </div>

          <div v-if="filterType === 'user'" class="control-group fade-in">
            <label>Rechercher un Utilisateur</label>
            <div class="user-search-container">
              <div class="input-with-icon">
                <Search size="18" />
                <input 
                  type="text" 
                  v-model="userSearchQuery" 
                  @input="searchUsers" 
                  placeholder="Nom, prénom ou email..."
                >
              </div>
              <div class="user-dropdown" v-if="userResults.length > 0">
                <div 
                  v-for="u in userResults" 
                  :key="u.id" 
                  @click="selectUser(u)"
                  class="user-option"
                >
                  <strong>{{ u.full_name }}</strong>
                  <span>@{{ u.username }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="actions">
          <button 
            class="action-btn danger-btn" 
            @click="triggerReanalysis" 
            :disabled="isLoading || (filterType === 'tag' && !filterTag) || (filterType === 'user' && !selectedUser)"
            id="btn-launch-reanalysis"
          >
            <RefreshCw :class="{ spin: isLoading }" size="20" />
            {{ isLoading ? 'Réanalyse en cours...' : 'Lancer la Réanalyse' }}
          </button>
          <button
            v-if="isLoading"
            class="action-btn reset-btn"
            @click="resetReanalysisLock"
            id="btn-reset-reanalysis-lock"
            title="Forcer la réinitialisation du verrou si la tâche est bloquée"
          >
            <Unlock size="16" />
            Écraser le verrou (tâche zombie)
          </button>
        </div>
      </div>

      <!-- Section 3: Logs & Résultats (Full Width) -->
      <div class="glass-panel logs-panel full-width">
        <div class="panel-header">
          <h3><Search size="20" /> Journal d'Exécution</h3>
          <div v-if="isLoading" class="active-badge pulse">Opération en cours...</div>
        </div>
        <div class="logs-container" ref="logContainer">
          <div v-if="logs.length === 0" class="empty-logs">Aucune opération en cours.</div>
          <div v-for="(log, i) in logs" :key="i" class="log-entry" 
               :class="{ 
                 'error-log': log.includes('ERREUR') || log.includes('ÉCHEC'),
                 'warn-log': log.includes('⚠️'),
                 'success-log': log.includes('TERMINÉ') || log.includes('Finished')
               }">
            {{ log }}
          </div>
        </div>
      </div>
    </div>

    <!-- Tree Preview Section -->
    <div class="tree-grid fade-in-up" v-if="treeResult">
      <div class="tree-header">
         <div style="display: flex; align-items: center; gap: 1.25rem;">
           <Network size="24" class="tree-icon" /> 
           <div>
             <h3>Nouvel Arbre de Compétences Généré</h3>
             <span class="subtitle-tag">Ceci est une prévisualisation de la taxonomie fusionnée.</span>
           </div>
         </div>
         <div v-if="treeCost" class="tree-cost-badge">
           Coût de l'opération : ${{ Number(treeCost).toFixed(4) }}
         </div>
      </div>
      <div class="tree-content">
         <pre class="json-viewer">{{ JSON.stringify(treeResult, null, 2) }}</pre>
      </div>
      <div class="tree-actions">
         <button @click="applyTree" class="action-btn success-btn" :disabled="isTreeLoading">
            <CheckCircle2 size="18" /> Appliquer cette Taxonomie
         </button>
      </div>
    </div>

    <div v-if="error" class="error-toast fade-in-up">
      <AlertTriangle size="20" />
      <span>{{ error }}</span>
    </div>

    <div v-if="successMessage" class="success-toast fade-in-up">
      <CheckCircle2 size="20" />
      <span>{{ successMessage }}</span>
    </div>
  </div>
</template>

<style scoped>
.reanalysis-wrapper {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
}

.header-banner {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-radius: 20px;
  padding: 2rem;
  color: white;
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 2rem;
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.2);
  position: relative;
}

.banner-icon {
  background: rgba(227, 25, 55, 0.2);
  padding: 1rem;
  border-radius: 16px;
  color: var(--zenika-red);
}

.banner-text h2 {
  font-size: 1.6rem;
  font-weight: 700;
  margin: 0 0 0.5rem 0;
}

.banner-text p {
  color: #94a3b8;
  margin: 0;
  font-size: 1rem;
}

.status-badge {
  position: absolute;
  top: 1.25rem;
  right: 1.25rem;
  background: rgba(59, 130, 246, 0.15);
  color: #60a5fa;
  padding: 0.4rem 0.8rem;
  border-radius: 30px;
  font-size: 0.75rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(96, 165, 250, 0.3);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

.full-width {
  grid-column: span 2;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(20px);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  padding: 1.5rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.glass-panel:hover {
  transform: translateY(-5px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.08);
}

.tree-panel {
  border-left: 4px solid #6366f1;
}

.cv-panel {
  border-left: 4px solid var(--zenika-red);
}

.section-desc {
  font-size: 0.9rem;
  color: #64748b;
  margin-bottom: 2rem;
  line-height: 1.5;
}

.panel-header h3 {
  font-size: 1.1rem;
  font-weight: 700;
  color: #1a1a1a;
  margin-bottom: 1.5rem;
  display: flex;
  align-items: center;
  gap: 10px;
}
.panel-header h3 svg { color: var(--zenika-red); }

.filter-controls {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  flex: 1;
}

.control-group label {
  display: block;
  font-size: 0.85rem;
  font-weight: 600;
  color: #4b5563;
  margin-bottom: 0.5rem;
}

.filter-pills {
  display: flex;
  background: #f1f5f9;
  padding: 4px;
  border-radius: 10px;
  gap: 4px;
}

.filter-pills button {
  flex: 1;
  border: none;
  background: transparent;
  padding: 0.6rem;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-pills button.active {
  background: white;
  color: var(--zenika-red);
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

.input-with-icon {
  position: relative;
  display: flex;
  align-items: center;
}

.input-with-icon svg {
  position: absolute;
  left: 12px;
  color: #94a3b8;
}

.input-with-icon input {
  width: 100%;
  padding: 0.75rem 0.75rem 0.75rem 2.5rem;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: white;
  font-size: 0.95rem;
  transition: all 0.2s;
}

.input-with-icon input:focus {
  outline: none;
  border-color: var(--zenika-red);
  box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1);
}

.user-search-container {
  position: relative;
}

.user-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  margin-top: 8px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.1);
  z-index: 10;
  max-height: 200px;
  overflow-y: auto;
}

.user-option {
  padding: 0.8rem 1rem;
  display: flex;
  flex-direction: column;
  cursor: pointer;
  transition: all 0.1s;
}

.user-option:hover {
  background: #f8fafc;
}

.user-option strong { font-size: 0.9rem; color: #1e293b; }
.user-option span { font-size: 0.75rem; color: #64748b; }

.actions {
  margin-top: 2rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.action-btn {
  width: 100%;
  padding: 1rem;
  border-radius: 12px;
  border: none;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.danger-btn {
  background: var(--zenika-red);
  color: white;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.3);
}

.danger-btn:hover:not(:disabled) {
  background: #c3132e;
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(227, 25, 55, 0.4);
}

.secondary-btn {
  background: white;
  border: 1px solid #e2e8f0;
  color: #1e293b;
}

.secondary-btn:hover:not(:disabled) {
  border-color: var(--zenika-red);
  color: var(--zenika-red);
}

.reset-btn {
  background: rgba(251, 146, 60, 0.1);
  border: 1px dashed #fb923c;
  color: #ea580c;
  font-size: 0.82rem;
  padding: 0.6rem 1rem;
  opacity: 0.85;
  transition: all 0.2s;
}

.reset-btn:hover {
  background: rgba(251, 146, 60, 0.2);
  opacity: 1;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(251, 146, 60, 0.2);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.logs-panel {
  display: flex;
  flex-direction: column;
}

.logs-container {
  flex: 1;
  background: #0f172a;
  border-radius: 12px;
  padding: 1rem;
  color: #38bdf8;
  font-family: 'Fira Code', 'Monaco', monospace;
  font-size: 0.8rem;
  overflow-y: auto;
  min-height: 300px;
  max-height: 400px;
  box-shadow: inset 0 2px 10px rgba(0,0,0,0.5);
}

.empty-logs {
  color: #64748b;
  font-style: italic;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.log-entry {
  padding: 6px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  line-height: 1.4;
  white-space: pre-wrap;
}

.error-log { color: #f87171; font-weight: 600; }
.warn-log { color: #fbbf24; background: rgba(251, 191, 36, 0.1); padding: 8px; border-radius: 4px; border-left: 3px solid #fbbf24; margin: 4px 0; }
.success-log { color: #34d399; }

.active-badge {
  font-size: 0.75rem;
  background: rgba(227, 25, 55, 0.1);
  color: var(--zenika-red);
  padding: 4px 12px;
  border-radius: 20px;
  font-weight: 700;
  text-transform: uppercase;
}

.pulse {
  animation: pulse-soft 2s infinite;
}

@keyframes pulse-soft {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.tree-grid {
  background: white;
  border-radius: 20px;
  border: 1px solid #e2e8f0;
  padding: 2rem;
  margin-top: 2rem;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
}

.tree-header {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin-bottom: 1.5rem;
}

.tree-icon {
  color: var(--zenika-red);
  background: rgba(227, 25, 55, 0.08);
  padding: 12px;
  border-radius: 12px;
}

.tree-header h3 { font-size: 1.4rem; color: #1e293b; margin: 0; }
.subtitle-tag { font-size: 0.85rem; color: #64748b; }

.tree-cost-badge {
  background: rgba(227, 25, 55, 0.1);
  color: var(--zenika-red);
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 700;
  margin-left: auto;
}

.json-viewer {
  background: #0f172a;
  border-radius: 12px;
  padding: 1.5rem;
  font-size: 0.85rem;
  color: #e2e8f0;
  max-height: 400px;
  overflow: auto;
}

.tree-actions {
  margin-top: 1.5rem;
  display: flex;
  justify-content: flex-end;
}

.success-btn {
  background: #10b981;
  color: white;
  padding: 0.8rem 1.5rem;
}

.error-toast, .success-toast {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  padding: 1rem 1.5rem;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.1);
  z-index: 100;
  font-weight: 600;
}

.error-toast { background: #fef2f2; color: #ef4444; border: 1px solid #fee2e2; }
.success-toast { background: #ecfdf5; color: #10b981; border: 1px solid #d1fae5; }

.spin { animation: spin 1s linear infinite; }
.pulse-animation { animation: pulse 1.5s ease-in-out infinite; }

@keyframes spin { 100% { transform: rotate(360deg); } }
@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.2); opacity: 0.7; }
  100% { transform: scale(1); opacity: 1; }
}

.fade-in { animation: fadeIn 0.4s ease forwards; }
.fade-in-up { animation: fadeInUp 0.5s ease forwards; }

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

@media (max-width: 900px) {
  .dashboard-grid { grid-template-columns: 1fr; }
}
</style>
