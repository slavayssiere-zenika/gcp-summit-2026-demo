<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import PageHeader from '../components/ui/PageHeader.vue'
import TaxonomySuggestions from '../components/TaxonomySuggestions.vue'
import { Server, Settings, CheckCircle, RefreshCcw, Search, Network, X, Trash2 } from 'lucide-vue-next'
import { authService } from '../services/auth'

const isAdmin = () => authService.state.user?.role === 'admin'

const successMessage = ref('')
const error = ref('')
const isLoading = ref(false)

const logs = ref<string[]>([])
const logContainer = ref<HTMLElement | null>(null)

const isTreeLoading = ref(false)
const treeStatus = ref('idle') // idle, running, waiting_for_user, completed, error
const treeArtifacts = ref<any>({})
const treePollingInterval = ref<any>(null)
const treeCost = ref<number | null>(null)
const batchProgress = ref<any>(null)
let lastBatchCheck = 0

const batchHistory = ref<any[]>([])
const isBatchHistoryLoading = ref(false)

const fetchBatchHistory = async () => {
  isBatchHistoryLoading.value = true
  try {
    const resp = await axios.get('/api/cv/recalculate_tree/batch/list')
    if (resp.data && resp.data.success) {
      batchHistory.value = resp.data.batches || []
    }
  } catch (e) {
    console.error('Failed to fetch batch history', e)
  } finally {
    isBatchHistoryLoading.value = false
  }
}

const deleteBatchJob = async (jobName: string) => {
  if (!confirm('Êtes-vous sûr de vouloir supprimer ce job de l\'historique GCP ?')) return;
  const jobId = jobName.split('/').pop()
  isBatchHistoryLoading.value = true
  try {
    const resp = await axios.delete(`/api/cv/recalculate_tree/batch/${jobId}`)
    if (resp.data && resp.data.success) {
      addLog(`Job supprimé: ${jobId}`)
      await fetchBatchHistory()
    } else {
      addLog(`Erreur suppression: ${resp.data?.error}`)
    }
  } catch (e: any) {
    console.error('Failed to delete batch job', e)
    addLog(`Erreur réseau (Suppression): ${e.message}`)
  } finally {
    isBatchHistoryLoading.value = false
  }
}

const checkBatchProgress = async () => {
  try {
    const resp = await axios.post('/api/cv/recalculate_tree/batch/check')
    if (resp.data && resp.data.progress) {
      batchProgress.value = resp.data.progress
      batchProgress.value.step = resp.data.step
      batchProgress.value.state = resp.data.state
      batchProgress.value.elapsed = resp.data.elapsed || ''
    }
  } catch (e) {
    console.error('Failed to check batch progress', e)
  }
}

const recoverBatch = async () => {
  try {
    const resp = await axios.post('/api/cv/recalculate_tree/batch/recover')
    if (resp.data && resp.data.success) {
      addLog('Reprise du batch forcée...')
      await checkTreeTaskStatus()
    } else {
      addLog(`Impossible de reprendre le batch: ${resp.data?.error}`)
    }
  } catch (e: any) {
    console.error('Failed to recover batch', e)
    addLog(`Erreur réseau (Reprise): ${e.message}`)
  }
}

const resetBatch = async () => {
  if (!confirm('⚠️ Réinitialiser l\'interface ? L\'état Redis sera effacé. Le job GCP en cours (s\'il existe) continuera de tourner. Utilisez \'Annuler\' d\'abord si vous voulez l\'arrêter.')) return
  try {
    const resp = await axios.post('/api/cv/recalculate_tree/batch/reset')
    if (resp.data && resp.data.success) {
      treeStatus.value = 'idle'
      addLog('✅ État du pipeline réinitialisé. Vous pouvez relancer un nouveau batch.')
      if (treePollingInterval.value) {
        clearInterval(treePollingInterval.value)
        treePollingInterval.value = null
      }
    } else {
      addLog(`Erreur reset: ${resp.data?.error}`)
    }
  } catch (e: any) {
    console.error('Failed to reset batch', e)
    addLog(`Erreur réseau (Reset): ${e.message}`)
  }
}

const addLog = (msg: string) => {
  const timestamp = new Date().toLocaleTimeString()
  logs.value.unshift(`[${timestamp}] ${msg}`)
  if (logs.value.length > 50) logs.value.pop()
}

const triggerTreeStep = async (step: str, target_pillar?: string) => {
  isTreeLoading.value = true
  error.value = ''
  addLog(`Lancement de l'étape: ${step}...`)
  
  try {
    await axios.post(`/api/cv/recalculate_tree/step`, { step, target_pillar })
    checkTreeTaskStatus()
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || `Erreur lors de l'étape ${step}`
    addLog(`ERREUR: ${error.value}`)
    isTreeLoading.value = false
  }
}

const checkTreeTaskStatus = async () => {
  try {
    const resp = await axios.get('/api/cv/recalculate_tree/status')
    const data = resp.data
    
    if (data && data.status) {
        treeStatus.value = data.status
        treeArtifacts.value = {
            map_result: data.map_result,
            res_tree: data.res_tree,
            sweep_result: data.sweep_result,
            completed_pillars: data.completed_pillars || [],
            missing_competencies: data.missing_competencies || []
        }
        treeCost.value = data.usage?.estimated_cost_usd || null

        if (data.logs && data.logs.length > 0) {
            const latestLog = data.logs[data.logs.length - 1]
            const msg = latestLog.includes('] ') ? latestLog.split('] ')[1] : latestLog
            if (logs.value.length === 0 || !logs.value[0].includes(msg)) {
                addLog(msg)
            }
        }
    }
    
    if (treeStatus.value === 'running' || treeStatus.value === 'batch_running') {
      isTreeLoading.value = true
      if (!treePollingInterval.value) {
        treePollingInterval.value = setInterval(checkTreeTaskStatus, 3000)
      }
      
      if (treeStatus.value === 'batch_running') {
        const now = Date.now()
        if (now - lastBatchCheck > 15000) {
          lastBatchCheck = now
          checkBatchProgress()
        }
      }
    } else {
      isTreeLoading.value = false
      if (treePollingInterval.value) {
        clearInterval(treePollingInterval.value)
        treePollingInterval.value = null
      }
      if (treeStatus.value === 'error') {
        error.value = data.error || "Erreur lors du calcul"
      }
    }
  } catch (e) {
    console.error('Failed to check tree task status', e)
  }
}

const startTreeBatch = async () => {
  isTreeLoading.value = true
  error.value = ''
  lastBatchCheck = 0  // Reset pour que le premier checkBatchProgress() s'exécute immédiatement
  addLog('Lancement du traitement Batch complet...')
  
  try {
    const resp = await axios.post('/api/cv/recalculate_tree/batch/start')
    if (resp.data && !resp.data.success) {
      addLog(`⚠️ ${resp.data.message || 'Erreur au lancement'}`)
      isTreeLoading.value = false
      return
    }
    // Déclencher immédiatement un check de statut qui mettra à jour treeStatus -> batch_running
    checkTreeTaskStatus()
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || 'Erreur lors du lancement Batch'
    addLog(`ERREUR: ${error.value}`)
    isTreeLoading.value = false
  }
}

const cancelTreeBatch = async () => {
    if (!confirm('Êtes-vous sûr de vouloir interrompre ce traitement Batch ?')) return;
    
    try {
        const resp = await axios.post('/api/cv/recalculate_tree/batch/cancel')
        if (resp.data && resp.data.success) {
            treeStatus.value = 'error'
            addLog('Traitement annulé par l\'utilisateur.')
            if (treePollingInterval.value) {
                clearInterval(treePollingInterval.value)
                treePollingInterval.value = null
            }
        } else {
            addLog(`Erreur annulation: ${resp.data?.error || 'Inconnue'}`)
        }
    } catch (e: any) {
        console.error('Erreur annulation:', e)
        addLog(`Erreur réseau (Cancel): ${e.message}`)
    }
}

const cancelInteractiveTree = async () => {
    if (!confirm('Êtes-vous sûr de vouloir interrompre ce traitement interactif ? (L\'opération s\'arrêtera à la fin de la requête en cours)')) return;
    
    try {
        const resp = await axios.post('/api/cv/recalculate_tree/cancel')
        if (resp.data && resp.data.success) {
            treeStatus.value = 'error'
            addLog('Annulation demandée. Le processus s\'arrêtera sous peu.')
            if (treePollingInterval.value) {
                clearInterval(treePollingInterval.value)
                treePollingInterval.value = null
            }
        } else {
            addLog(`Erreur annulation: ${resp.data?.error || 'Inconnue'}`)
        }
    } catch (e: any) {
        console.error('Erreur annulation:', e)
        addLog(`Erreur réseau (Cancel): ${e.message}`)
    }
}

onMounted(() => {
  checkTreeTaskStatus()
  fetchBatchHistory()
})

onUnmounted(() => {
  if (treePollingInterval.value) {
    clearInterval(treePollingInterval.value)
  }
})
</script>

<template>
  <div class="reanalysis-wrapper fade-in">
    <PageHeader
      title="Taxonomie & Structure IA"
      subtitle="Reconstruisez la taxonomie globale des compétences basée sur le contenu des CVs."
      :icon="Network"
      :breadcrumb="[
        { label: 'Administration', to: '/admin' },
        { label: 'Taxonomie & Structure IA' }
      ]"
    />

    <TaxonomySuggestions />

    <div class="dashboard-grid">
      <!-- Section 1: Recalcul de l'Arbre -->
      <div class="glass-panel tree-panel">
        <div class="panel-header">
          <h3><Network size="20" /> Taxonomie Interactive (Human-in-the-Loop)</h3>
        </div>
        <div class="panel-content">
          <p class="section-desc">Ce processus génère une taxonomie en 4 étapes interactives. Vous pouvez valider chaque étape.</p>
          
          <div class="step-wizard" v-if="treeStatus !== 'idle'">
             <div class="step-status">Status actuel : <strong>{{ treeStatus }}</strong></div>
             
             <!-- Étape 1 & 2 : Map & Dedup -->
             <div class="step-box" v-if="treeArtifacts.map_result && Object.keys(treeArtifacts.res_tree || {}).length === 0">
                <h4>Étape 1 & 2 : Piliers (Map & Dedup)</h4>
                <div class="artifact-cards">
                    <div v-for="(skills, pillar) in treeArtifacts.map_result" :key="pillar" class="artifact-card">
                        <div class="card-title">{{ pillar }} <span class="badge">{{ skills.length }}</span></div>
                        <div class="tags-container">
                            <span v-for="skill in skills" :key="skill" class="skill-tag">{{ skill }}</span>
                        </div>
                    </div>
                </div>
                <div class="actions" v-if="treeStatus === 'waiting_for_user' || treeStatus === 'error' || treeStatus === 'cancelled'">
                    <button class="action-btn secondary-btn" @click="triggerTreeStep('deduplicate')">Relancer la déduplication</button>
                    <button class="action-btn primary-btn" @click="triggerTreeStep('reduce')">Valider les piliers et passer à Reduce</button>
                </div>
             </div>

             <!-- Étape 3 : Reduce -->
             <div class="step-box" v-if="Object.keys(treeArtifacts.res_tree || {}).length > 0 && (treeArtifacts.sweep_result === undefined || treeArtifacts.sweep_result === null)">
                <h4>Étape 3 : Arbre (Reduce)</h4>
                <p>Piliers traités : {{ treeArtifacts.completed_pillars?.join(', ') || 'Aucun' }}</p>
                <div class="artifact-cards">
                    <div v-for="(node, pillar) in treeArtifacts.res_tree" :key="pillar" class="artifact-card">
                        <div class="card-title">{{ node.name || pillar }}</div>
                        <div class="tree-nodes">
                            <div v-for="sub in node.sub_competencies" :key="sub.name" class="tree-node">
                                <strong>{{ sub.name }}</strong>
                                <span v-if="sub.aliases" style="font-size: 0.75rem; color: #64748b;"> ({{ sub.aliases }})</span>
                                <div v-if="sub.merge_from && sub.merge_from.length" class="merge-tags">
                                    <span v-for="m in sub.merge_from" :key="m" class="merge-tag">fusionner: {{ m }}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="actions" v-if="treeStatus === 'waiting_for_user' || treeStatus === 'error' || treeStatus === 'cancelled'">
                    <button class="action-btn secondary-btn" @click="triggerTreeStep('sweep')">Passer au Sweep (Rattrapage)</button>
                </div>
             </div>

             <!-- Étape 4 : Sweep -->
             <div class="step-box" v-if="treeArtifacts.sweep_result !== undefined && treeArtifacts.sweep_result !== null">
                <h4>Étape 4 : Rattrapage (Sweep)</h4>
                <p v-if="treeArtifacts.missing_competencies?.length">Orphelines trouvées: {{ treeArtifacts.missing_competencies.length }}</p>
                <div class="artifact-cards">
                    <div v-for="item in treeArtifacts.sweep_result" :key="item.name" class="artifact-card">
                        <div class="card-title"><strong>{{ item.name }}</strong></div>
                        <div class="tags-container" v-if="item.merge_from && item.merge_from.length">
                            <span style="font-size: 0.75rem; color: #64748b; margin-top: 4px;">À fusionner depuis :</span>
                            <span v-for="m in item.merge_from" :key="m" class="merge-tag">← {{ m }}</span>
                        </div>
                    </div>
                </div>
                <div class="actions" v-if="treeStatus === 'waiting_for_user' || treeStatus === 'error' || treeStatus === 'cancelled'">
                    <button class="action-btn primary-btn" @click="triggerTreeStep('apply')">Appliquer et Sauvegarder</button>
                </div>
             </div>
          </div>
          
          <div class="actions" v-if="['idle', 'error', 'completed', 'cancelled'].includes(treeStatus)">
            <button 
              class="action-btn secondary-btn" 
              @click="triggerTreeStep('map')"
              :disabled="isLoading || isTreeLoading || treeStatus === 'batch_running' || !isAdmin()"
              :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Démarrer la taxonomie (Mode Interactif)'"
            >
              <Network size="20" :class="{ 'pulse-animation': isTreeLoading && treeStatus !== 'batch_running' }" />
              {{ isTreeLoading && treeStatus !== 'batch_running' ? 'Calcul en cours...' : "Démarrer la taxonomie (Mode Interactif)" }}
            </button>
            
            <button 
              class="action-btn primary-btn" 
              @click="startTreeBatch()"
              :disabled="isLoading || isTreeLoading || treeStatus === 'batch_running' || !isAdmin()"
              :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Planifier un recalcul complet (Mode Batch - Coût Réduit)'"
              style="margin-top: 1rem; background: #6366f1;"
            >
              <Network size="20" :class="{ 'pulse-animation': treeStatus === 'batch_running' }" />
              {{ treeStatus === 'batch_running' ? 'Processus Batch en cours côté serveur...' : "Planifier un recalcul complet (Mode Batch - Coût Réduit)" }}
            </button>
            
            <button 
              v-if="treeStatus === 'error'"
              class="action-btn secondary-btn" 
              @click="recoverBatch"
              :disabled="!isAdmin()"
              :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Forcer Reprise du Batch'"
              style="margin-top: 1rem; border-color: #ef4444; color: #ef4444;"
            >
              <RefreshCcw size="20" />
              Forcer Reprise du Batch (Suite à Erreur/Timeout)
            </button>
            <button 
              v-if="treeStatus !== 'batch_running' && treeStatus !== 'running'"
              class="action-btn secondary-btn" 
              @click="resetBatch"
              :disabled="!isAdmin()"
              :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Réinitialiser état'"
              style="margin-top: 1rem; border-color: #94a3b8; color: #94a3b8; font-size: 0.8rem;"
            >
              🔄 Réinitialiser l'état (Urgence)
            </button>
          </div>

          <div class="actions" v-if="treeStatus === 'running'" style="display: flex; justify-content: space-between; align-items: center; margin-top: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem; color: #64748b;">
              <Activity size="20" class="pulse-animation" />
              <span>Calcul interactif en cours... (Actualisation auto)</span>
            </div>
            <button 
              class="action-btn" 
              @click="cancelInteractiveTree()"
              style="background: transparent; border: 1px solid #ef4444; color: #ef4444; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-weight: 500;"
            >
              <X size="18" style="vertical-align: middle; margin-right: 6px;" /> Interrompre
            </button>
          </div>
          
          <div v-if="treeStatus === 'batch_running'" class="step-box" style="margin-top: 1.5rem; background: rgba(99, 102, 241, 0.1); border: 1px solid #6366f1;">
              <h4 style="color: #6366f1;">Processus Batch Asynchrone en cours</h4>
              <p>Un recalcul automatique (Batch) est actuellement en cours par le système GCP. Cette opération peut prendre plusieurs heures (SLA: 24h). L'arbre sera automatiquement mis à jour à la fin du processus.</p>
              <p v-if="treeArtifacts.batch_job_id"><strong>ID du Job:</strong> {{ treeArtifacts.batch_job_id }}</p>
              
              <div v-if="batchProgress && batchProgress.total > 0" class="batch-progress" style="margin-top: 1rem;">
                  <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                      <span style="font-weight: 600;">Étape : {{ batchProgress.step?.toUpperCase() || 'Inconnue' }} ({{ batchProgress.state }})</span>
                      <span>{{ batchProgress.completed }} / {{ batchProgress.total }} ({{ batchProgress.percent }}%)</span>
                  </div>
                  <div style="width: 100%; background: #e2e8f0; border-radius: 4px; height: 12px; overflow: hidden;">
                      <div :style="{ width: batchProgress.percent + '%', background: '#6366f1', height: '100%', transition: 'width 0.3s ease' }"></div>
                  </div>
                  <p v-if="batchProgress.failed > 0" style="color: #ef4444; font-size: 0.85rem; margin-top: 0.5rem;">⚠️ {{ batchProgress.failed }} requête(s) en échec</p>
              </div>
              <div v-else style="margin-top: 1rem; color: #64748b; font-size: 0.85rem;">
                  <span v-if="batchProgress?.elapsed">⏱ Temps écoulé : <strong>{{ batchProgress.elapsed }}</strong> — </span>
                  <span>Vertex AI ne publie pas de compteur pendant l'exécution. Résultat disponible à la fin du job.</span>
              </div>
              
              <div style="margin-top: 1.5rem; text-align: right;">
                  <button 
                      class="action-btn" 
                      @click="cancelTreeBatch()"
                      :disabled="!isAdmin()"
                      :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Interrompre le traitement'"
                      style="background: transparent; border: 1px solid #ef4444; color: #ef4444; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-weight: 500;"
                  >
                      <X size="18" style="vertical-align: middle; margin-right: 6px;" /> Interrompre le traitement
                  </button>
              </div>
          </div>
        </div>
      </div>

      <!-- Section 2: Historique Batch (Nouveau Dashboard) -->
      <div class="glass-panel batch-panel">
        <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center;">
          <h3><Server size="20" /> Historique Jobs Batch GCP</h3>
          <button @click="fetchBatchHistory" class="action-btn secondary-btn" style="width: auto; padding: 0.4rem 0.8rem; font-size: 0.85rem;" :disabled="isBatchHistoryLoading">
             <RefreshCcw size="14" :class="{ 'spin': isBatchHistoryLoading }" /> Actualiser
          </button>
        </div>
        <div class="panel-content" style="flex: 1; overflow-y: auto; max-height: 400px; padding-right: 0.5rem;">
          <p v-if="batchHistory.length === 0 && !isBatchHistoryLoading" class="section-desc">Aucun job batch enregistré.</p>
          <div v-else class="batch-list" style="display: flex; flex-direction: column; gap: 1rem;">
             <div v-for="job in batchHistory" :key="job.name" class="artifact-card" style="position: relative; overflow: hidden;">
                 <div style="position: absolute; top: 0; left: 0; width: 4px; height: 100%;" 
                      :style="{ background: job.state === 'JOB_STATE_SUCCEEDED' ? '#10b981' : (job.state === 'JOB_STATE_FAILED' ? '#ef4444' : '#3b82f6') }"></div>
                 <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                    <div>
                        <strong style="font-size: 0.95rem;">{{ job.display_name || job.name.split('/').pop() }}</strong>
                        <div style="font-size: 0.75rem; color: #64748b; margin-top: 2px;">ID: {{ job.name.split('/').pop() }}</div>
                    </div>
                    <div style="display: flex; gap: 0.5rem; align-items: center; position: relative; top: 0; right: 0;">
                        <span class="status-badge"
                              :style="{ color: job.state === 'JOB_STATE_SUCCEEDED' ? '#10b981' : (job.state === 'JOB_STATE_FAILED' ? '#ef4444' : '#3b82f6'), 
                                        background: job.state === 'JOB_STATE_SUCCEEDED' ? 'rgba(16, 185, 129, 0.1)' : (job.state === 'JOB_STATE_FAILED' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(59, 130, 246, 0.1)'),
                                        borderColor: 'transparent', margin: 0 }">
                            {{ job.state.replace('JOB_STATE_', '') }}
                        </span>
                        <button v-if="isAdmin()" class="action-btn" @click.stop="deleteBatchJob(job.name)" title="Supprimer ce job"
                                style="padding: 4px; background: transparent; color: #ef4444; border: none; width: auto; min-width: auto; height: auto; cursor: pointer;">
                            <Trash2 size="16" />
                        </button>
                    </div>
                 </div>
                 
                 <div style="font-size: 0.8rem; color: #475569; display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.8rem;">
                     <div>🕐 Créé: {{ new Date(job.create_time).toLocaleString() }}</div>
                     <div v-if="job.start_time">▶️ Démarré: {{ new Date(job.start_time).toLocaleString() }}</div>
                     <div v-else-if="job.update_time">🔄 MàJ: {{ new Date(job.update_time).toLocaleString() }}</div>
                     <div v-if="job.end_time">✅ Terminé: {{ new Date(job.end_time).toLocaleString() }}</div>
                     <div v-if="job.model" style="grid-column: span 2; font-size: 0.72rem; color: #94a3b8;">Modèle: {{ job.model }}</div>
                 </div>
                 
                 <div v-if="job.completion_stats && job.completion_stats.total > 0" style="margin-top: 0.8rem;">
                     <div style="display: flex; justify-content: space-between; font-size: 0.75rem; margin-bottom: 4px;">
                         <span>✅ {{ job.completion_stats.successful }} réussies / {{ job.completion_stats.total }}</span>
                         <span v-if="job.completion_stats.failed > 0" style="color: #ef4444;">❌ {{ job.completion_stats.failed }} échec(s)</span>
                         <span v-if="job.completion_stats.incomplete > 0" style="color: #f59e0b;">⏳ {{ job.completion_stats.incomplete }} incomplet(s)</span>
                     </div>
                     <div style="width: 100%; background: #f1f5f9; border-radius: 4px; height: 6px; overflow: hidden;">
                         <div :style="{ width: job.completion_stats.percent + '%', background: job.completion_stats.failed > 0 ? '#f59e0b' : '#10b981', height: '100%' }"></div>
                     </div>
                 </div>
             </div>
          </div>
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
  box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.25);
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

/* Artifact Cards Styles */
.artifact-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
  margin: 1rem 0;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 0.5rem;
}

.artifact-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0,0,0,0.02);
}

.card-title {
  font-weight: 700;
  font-size: 0.95rem;
  color: #1e293b;
  margin-bottom: 0.75rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 0.5rem;
}

.badge {
  background: #eff6ff;
  color: #3b82f6;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.75rem;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.skill-tag {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 0.8rem;
  color: #475569;
}

.tree-nodes {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tree-node {
  font-size: 0.85rem;
  background: #f8fafc;
  padding: 0.5rem;
  border-radius: 8px;
  border-left: 3px solid #6366f1;
}

.merge-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.merge-tag {
  background: #fef2f2;
  color: #ef4444;
  border: 1px solid #fecaca;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.75rem;
}

/* Custom Scrollbar for artifact cards */
.artifact-cards::-webkit-scrollbar {
  width: 6px;
}
.artifact-cards::-webkit-scrollbar-track {
  background: #f1f5f9;
  border-radius: 4px;
}
.artifact-cards::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}
.artifact-cards::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
