<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { Settings, RefreshCw, Network, AlertTriangle, ShieldCheck, CheckCircle2 } from 'lucide-vue-next'
import { authService } from '../services/auth'
import DriveAdminPanel from '../components/DriveAdminPanel.vue'

const isLoading = ref(false)
const error = ref('')
const successResponse = ref<any>(null)

const triggerRemapping = async () => {
  if (confirm("Générer la nouvelle taxonomie écrasera votre affichage actuel (sans corrompre l'historique physique). Êtes-vous sûr ?")) {
    isLoading.value = true
    error.value = ''
    successResponse.value = null
    
    try {
      const resp = await axios.post('/cv-api/cvs/recalculate_tree')
      // The response natively contains {"tree": { ... }} matching from FastAPI Schema
      successResponse.value = resp.data.tree || resp.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || "Erreur lors de la communication sécurisée avec l'API"
    } finally {
      isLoading.value = false
    }
  }
}

const applySuccess = ref(false)

const applyRemapping = async () => {
  isLoading.value = true
  error.value = ''
  applySuccess.value = false
  
  try {
    await axios.post('/comp-api/competencies/bulk_tree', { tree: successResponse.value })
    applySuccess.value = true
    successResponse.value = null // Hide tree layout after active deploy
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || "Erreur de synchro DB PostgreSQL"
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="admin-wrapper fade-in">
    <div class="header-banner">
      <div class="banner-icon"><Settings size="32" /></div>
      <div class="banner-text">
        <h2>Centre d'Administration Sécurisé</h2>
        <p>Espace réservé aux opérateurs système pour piloter les fonctions AI massives de la plateforme.</p>
      </div>
      <div class="status-badge" v-if="authService.state.user?.role === 'admin'">
        <ShieldCheck size="16" /> Rôle Vérifié
      </div>
    </div>

    <div class="dashboard-grid">
      <DriveAdminPanel />

      <!-- Moteur Taxonomique Core -->
      <div class="glass-panel">
        <div class="panel-header">
          <h3><Network size="20" /> Modeleur RAG de Compétences (Generative AI)</h3>
        </div>
        <div class="panel-body">
          <p class="description">
            Ce processus déclenche une analyse exhaustive de l'ensemble des fragments textuels stockés dans la base de données CV.
            Gemini va recomposer nativement la structure hiérarchique idéale des compétences de vos collaborateurs.
          </p>
          
          <div class="alert-warning">
            <AlertTriangle size="16" />
            <span>Attention, cette opération sollicite massivement la clé d'API Google et peut prendre jusqu'à 60 secondes en facturation Deep Learning.</span>
          </div>

          <button 
            @click="triggerRemapping" 
            class="action-btn" 
            :disabled="isLoading"
          >
            <RefreshCw v-if="isLoading" class="spin" size="18" />
            <Network v-else size="18" />
            {{ isLoading ? 'Analyse Gemini en cours...' : 'Forcer le Recalcul de l\'Arbre' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Tree UI Render Engine -->
    <div class="tree-grid fade-in-up" v-if="successResponse">
      <div class="tree-header">
         <Network size="24" class="tree-icon" /> 
         <div>
           <h3>Taxonomie Officielle Générée</h3>
           <span class="subtitle-tag">Exporté via Gemini 1.5 Pro</span>
         </div>
      </div>
      <div class="tree-content">
         <pre class="json-viewer">{{ JSON.stringify(successResponse, null, 2) }}</pre>
      </div>
      <div class="tree-actions">
         <button @click="applyRemapping" class="action-btn success-btn" :disabled="isLoading">
            <CheckCircle2 size="18" /> Sauvegarder et Écraser l'Arbre en DB
         </button>
      </div>
    </div>

    <!-- Success Output -->
    <div class="success-panel fade-in-up" v-if="applySuccess">
       <CheckCircle2 size="24" />
       <div>
         <strong>Déploiement Terminé :</strong> La taxonomie a été appliquée sur la base et les caches backend distribués ont été vidés de manière asynchrone. Les consultants héritent instantanément de l'affichage.
       </div>
    </div>

    <div class="error-panel fade-in-up" v-if="error">
       <strong>Erreur IAM :</strong> {{ error }}
    </div>

  </div>
</template>

<style scoped>
.admin-wrapper {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem;
}

.header-banner {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-radius: 20px;
  padding: 2.5rem;
  color: white;
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 2.5rem;
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.2);
  position: relative;
  overflow: hidden;
}

.banner-icon {
  background: rgba(227, 25, 55, 0.2);
  padding: 1.25rem;
  border-radius: 16px;
  color: var(--zenika-red);
}

.banner-text h2 {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0 0 0.5rem 0;
}

.banner-text p {
  color: #94a3b8;
  margin: 0;
  font-size: 1.05rem;
}

.status-badge {
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  padding: 0.5rem 1rem;
  border-radius: 30px;
  font-size: 0.85rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(52, 211, 153, 0.3);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.5);
  backdrop-filter: blur(20px);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  padding: 2rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

.panel-header h3 {
  font-size: 1.25rem;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 1.5rem 0;
  display: flex;
  align-items: center;
  gap: 12px;
}
.panel-header h3 svg {
  color: var(--zenika-red);
}

.description {
  color: #475569;
  font-size: 1rem;
  line-height: 1.6;
  margin-bottom: 1.5rem;
}

.alert-warning {
  background: rgba(245, 158, 11, 0.1);
  border-left: 4px solid #f59e0b;
  padding: 1rem 1.25rem;
  border-radius: 0 12px 12px 0;
  color: #b45309;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 2rem;
}

.action-btn {
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 1rem 2rem;
  border-radius: 12px;
  font-size: 1.05rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: all 0.2s ease;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.3);
}

.action-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(227, 25, 55, 0.4);
  background: #c3132e;
}

.action-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  100% { transform: rotate(360deg); }
}

/* Tree Render Logic */
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
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 1.5rem;
}

.tree-icon {
  color: var(--zenika-red);
  background: rgba(227, 25, 55, 0.08);
  padding: 12px;
  border-radius: 12px;
  width: 48px;
  height: 48px;
}

.tree-header h3 {
  font-size: 1.4rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
}

.subtitle-tag {
  font-size: 0.85rem;
  color: #64748b;
  font-weight: 500;
  display: inline-block;
  margin-top: 4px;
}

.json-viewer {
  background: #0f172a;
  border-radius: 12px;
  padding: 2rem;
  font-family: 'MesloLGS NF', 'Fira Code', monospace;
  font-size: 0.95rem;
  color: #e2e8f0;
  overflow-x: auto;
  border: 1px solid rgba(255,255,255,0.1);
  box-shadow: inset 0 4px 20px rgba(0,0,0,0.5);
  line-height: 1.5;
}

.error-panel {
  margin-top: 2rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 1.5rem;
  border-radius: 12px;
  color: #b91c1c;
  display: flex;
  gap: 10px;
}

.success-panel {
  margin-top: 2rem;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.3);
  padding: 1.5rem;
  border-radius: 12px;
  color: #059669;
  display: flex;
  align-items: center;
  gap: 15px;
}

.tree-actions {
  margin-top: 1.5rem;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid #f1f5f9;
  padding-top: 1.5rem;
}

.success-btn {
  background: #10b981;
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
}
.success-btn:hover:not(:disabled) {
  background: #059669;
  box-shadow: 0 8px 20px rgba(16, 185, 129, 0.4);
}

.fade-in {
  animation: fadeIn 0.4s ease forwards;
}
.fade-in-up {
  animation: fadeInUp 0.5s ease forwards;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
