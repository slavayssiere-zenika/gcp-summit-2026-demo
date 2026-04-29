<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
import { AlertTriangle, Users, CheckCircle2, RotateCw, GitMerge, Search } from 'lucide-vue-next'
import { authService } from '../services/auth'
import PageHeader from '../components/ui/PageHeader.vue'

const isLoading = ref(false)
const error = ref('')
const successResponse = ref('')
const duplicates = ref<any[]>([])

const fetchDuplicates = async () => {
  isLoading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/users/duplicates', {
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    
    // Check if the response contains items to handle different pagination output optionally
    const duplicateData = Array.isArray(res.data) ? res.data : (res.data.items || [])
    
    duplicates.value = duplicateData.map((dup: any) => ({
      ...dup,
      target_id: null,
      source_id: null
    }))
  } catch (e: any) {
    error.value = e.response?.data?.detail || "Erreur de récupération des doublons"
  } finally {
    isLoading.value = false
  }
}

const performMerge = async (candidate: any) => {
  if (!candidate.target_id || !candidate.source_id) {
    error.value = "Veuillez sélectionner un compte source et un compte maître."
    return
  }
  if (candidate.target_id === candidate.source_id) {
    error.value = "Le compte source et maître ne peuvent pas être identiques."
    return
  }

  isLoading.value = true
  error.value = ''
  successResponse.value = ''
  try {
    await axios.post('/api/users/merge', {
      source_id: candidate.source_id,
      target_id: candidate.target_id
    }, {
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    successResponse.value = `Fusion réussie (source: ${candidate.source_id} -> cible: ${candidate.target_id})`
    await fetchDuplicates()
  } catch (e: any) {
    error.value = e.response?.data?.detail || "Erreur lors de la fusion."
  } finally {
    isLoading.value = false
  }
}
const activeTab = ref<'doublons' | 'anonymes'>('doublons')
const anonymousUsers = ref<any[]>([])
const isLoadingAnon = ref(false)

const fetchAnonymousUsers = async () => {
  isLoadingAnon.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/users/', {
      params: { is_anonymous: true, limit: 50 },
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    anonymousUsers.value = res.data.items || []
  } catch (e: any) {
    error.value = "Erreur de récupération des profils anonymes"
  } finally {
    isLoadingAnon.value = false
  }
}

watch(activeTab, (val) => {
  if (val === 'anonymes' && anonymousUsers.value.length === 0) {
    fetchAnonymousUsers()
  }
})

const selectedAnonForMerge = ref<number | null>(null)
const anonMergeSearchQuery = ref('')
const anonMergeSearchResults = ref<any[]>([])
const isSearchingAnonMerge = ref(false)
const selectedAnonMergeTarget = ref<number | null>(null)

const searchAnonMergeUsers = async () => {
  if (anonMergeSearchQuery.value.length < 2) return
  isSearchingAnonMerge.value = true
  try {
    const res = await axios.get('/api/users/search', {
      params: { query: anonMergeSearchQuery.value, limit: 5 },
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    anonMergeSearchResults.value = (res.data.items || []).filter((u: any) => !u.is_anonymous)
  } catch (err) {
    console.error('Search failed:', err)
  } finally {
    isSearchingAnonMerge.value = false
  }
}

const performAnonMerge = async () => {
  if (!selectedAnonForMerge.value || !selectedAnonMergeTarget.value) return
  
  isLoading.value = true
  error.value = ''
  successResponse.value = ''
  try {
    await axios.post('/api/users/merge', {
      source_id: selectedAnonForMerge.value,
      target_id: selectedAnonMergeTarget.value
    }, {
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    successResponse.value = `Désanonymisation réussie (ID: ${selectedAnonForMerge.value} -> ID: ${selectedAnonMergeTarget.value})`
    
    selectedAnonForMerge.value = null
    selectedAnonMergeTarget.value = null
    anonMergeSearchQuery.value = ''
    anonMergeSearchResults.value = []
    await fetchAnonymousUsers()
  } catch (e: any) {
    error.value = e.response?.data?.detail || "Erreur lors de la fusion."
  } finally {
    isLoading.value = false
  }
}

const createAnonForm = ref({ first_name: '', last_name: '', email: '' })

const transformAnonToUser = async (userId: number) => {
  isLoading.value = true
  error.value = ''
  successResponse.value = ''
  try {
    const updateData = {
      first_name: createAnonForm.value.first_name,
      last_name: createAnonForm.value.last_name,
      email: createAnonForm.value.email,
      full_name: `${createAnonForm.value.first_name} ${createAnonForm.value.last_name}`,
      is_anonymous: false
    }
    await axios.put(`/api/users/${userId}`, updateData, {
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    successResponse.value = `Profil créé avec succès pour ${updateData.full_name}.`
    selectedAnonForMerge.value = null
    createAnonForm.value = { first_name: '', last_name: '', email: '' }
    await fetchAnonymousUsers()
  } catch (e: any) {
    error.value = e.response?.data?.detail || "Erreur lors de la création du profil."
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  fetchDuplicates()
})
</script>

<template>
  <div class="admin-wrapper fade-in">

    <PageHeader
      title="Déduplication des Profils"
      subtitle="Fusionnez les comptes dupliqués pour garantir la cohérence des données et des vecteurs RAG."
      :icon="GitMerge"
      :breadcrumb="[
        { label: 'Hub RH', to: '/admin/availability' },
        { label: 'Déduplication Profils' }
      ]"
    />

    <!-- Success Output -->
    <div class="success-panel fade-in-up" v-if="successResponse">
       <CheckCircle2 size="24" />
       <div>
         <strong>Opération réussie :</strong> {{ successResponse }}
       </div>
    </div>
    
    <div class="error-panel fade-in-up" v-if="error">
       <strong>Erreur :</strong> {{ error }}
    </div>

    <div class="tabs-container">
      <button class="tab-btn" :class="{ active: activeTab === 'doublons' }" @click="activeTab = 'doublons'">
        Doublons Automatiques
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'anonymes' }" @click="activeTab = 'anonymes'">
        Profils Anonymes
      </button>
    </div>

    <div v-if="activeTab === 'doublons'" class="glass-panel mt-4">
      <div class="panel-header d-flex-between">
        <h3>Doublons Détectés ({{ duplicates.length }})</h3>
        <button @click="fetchDuplicates" class="action-btn-secondary" :disabled="isLoading">
          <RotateCw :class="{ 'spin': isLoading }" size="16" /> Rafraîchir
        </button>
      </div>

      <div v-if="duplicates.length === 0 && !isLoading" class="empty-state">
        <CheckCircle2 size="48" color="#10b981" />
        <p>Aucun doublon potentiel actif trouvé dans la base.</p>
      </div>

      <div v-for="(candidate, index) in duplicates" :key="index" class="duplicate-card">
        <h4 class="dup-title">Candidat trouvés</h4>
        <div class="users-grid">
           <div v-for="user in candidate.users" :key="user.id" class="user-item">
              <div class="user-info">
                 <RouterLink :to="'/user/' + user.id" class="text-link">
                   <strong>{{ user.full_name }}</strong>
                 </RouterLink>
                 <br/><span class="text-xs text-muted">ID: {{ user.id }} | Email: {{ user.email }} | Actif: {{ user.is_active }} | Créé: {{ new Date(user.created_at).toLocaleDateString() }}</span>
              </div>
           </div>
        </div>
        
        <div class="merge-controls">
           <div class="control-group">
              <label>Compte à SUPPRIMER (Source) :</label>
              <select v-model="candidate.source_id" class="form-select">
                <option :value="null">-- Choisir --</option>
                <option v-for="user in candidate.users" :key="'s'+user.id" :value="user.id">
                   {{ user.email }} (ID: {{ user.id }})
                </option>
              </select>
           </div>
           <div class="control-group">
              <label>Compte MAÎTRE (Cible) :</label>
              <select v-model="candidate.target_id" class="form-select">
                <option :value="null">-- Choisir --</option>
                <option v-for="user in candidate.users" :key="'t'+user.id" :value="user.id">
                   {{ user.email }} (ID: {{ user.id }})
                </option>
              </select>
           </div>
           <button @click="performMerge(candidate)" class="action-btn validate-btn" 
                   :disabled="!candidate.source_id || !candidate.target_id || candidate.source_id === candidate.target_id || isLoading">
              Lancer la Fusion
           </button>
        </div>
      </div>

    </div>

    <!-- The new glass-panel for anonymes -->
    <div v-if="activeTab === 'anonymes'" class="glass-panel mt-4">
      <div class="panel-header d-flex-between">
        <h3>Profils Anonymes ({{ anonymousUsers.length }})</h3>
        <button @click="fetchAnonymousUsers" class="action-btn-secondary" :disabled="isLoadingAnon">
          <RotateCw :class="{ 'spin': isLoadingAnon }" size="16" /> Rafraîchir
        </button>
      </div>

      <div v-if="anonymousUsers.length === 0 && !isLoadingAnon" class="empty-state">
        <CheckCircle2 size="48" color="#10b981" />
        <p>Aucun profil anonyme actif trouvé dans la base.</p>
      </div>

      <div v-for="user in anonymousUsers" :key="user.id" class="duplicate-card">
         <div class="d-flex-between" style="align-items: flex-start;">
           <div class="user-info">
             <RouterLink :to="'/user/' + user.id" class="text-link">
               <strong>{{ user.full_name }}</strong>
             </RouterLink>
             <br/><span class="text-xs text-muted">ID: {{ user.id }} | Email: {{ user.email }} | Créé: {{ new Date(user.created_at).toLocaleDateString() }}</span>
           </div>
           <button class="action-btn-secondary" style="border-color: var(--zenika-red); color: var(--zenika-red);" 
                   @click="selectedAnonForMerge = user.id" 
                   v-if="selectedAnonForMerge !== user.id">
             Désanonymiser
           </button>
           <button class="action-btn-secondary" @click="selectedAnonForMerge = null" v-else>
             Annuler
           </button>
         </div>

         <!-- Search block for merge -->
         <div v-if="selectedAnonForMerge === user.id" class="merge-controls mt-4" style="flex-direction: column; align-items: stretch;">
            <div style="display: flex; gap: 1.5rem; align-items: flex-end;">
                <div class="control-group" style="flex: 2;">
                   <label>1. Chercher un vrai profil existant (Cible) :</label>
                   <div style="display: flex; gap: 10px;">
                     <input type="text" v-model="anonMergeSearchQuery" placeholder="Nom, email..." class="form-select" @keyup.enter="searchAnonMergeUsers" style="flex:1;">
                     <button @click="searchAnonMergeUsers" class="action-btn-secondary" :disabled="isSearchingAnonMerge">
                       <Search size="16" />
                     </button>
                   </div>
                </div>
                <div class="control-group" v-if="anonMergeSearchResults.length > 0" style="flex: 2;">
                   <label>2. Sélectionner le profil maître :</label>
                   <select v-model="selectedAnonMergeTarget" class="form-select">
                     <option :value="null">-- Choisir --</option>
                     <option v-for="res in anonMergeSearchResults" :key="res.id" :value="res.id">
                        {{ res.full_name }} ({{ res.email }})
                     </option>
                   </select>
                </div>
                <button @click="performAnonMerge" class="action-btn validate-btn" 
                        :disabled="!selectedAnonMergeTarget || isLoading"
                        v-if="anonMergeSearchResults.length > 0" style="align-self: flex-end;">
                   Fusionner
                </button>
            </div>
            
            <hr style="margin: 1rem 0; border: none; border-top: 1px dashed rgba(227, 25, 55, 0.2);" />
            
            <div class="control-group">
               <label>Ou transformer ce profil anonyme en nouveau collaborateur complet :</label>
               <div style="display: flex; gap: 10px; align-items: flex-end;">
                 <div style="flex:1;"><input type="text" v-model="createAnonForm.first_name" placeholder="Prénom" class="form-select" style="width:100%;"></div>
                 <div style="flex:1;"><input type="text" v-model="createAnonForm.last_name" placeholder="Nom" class="form-select" style="width:100%;"></div>
                 <div style="flex:1;"><input type="email" v-model="createAnonForm.email" placeholder="Email Zenika" class="form-select" style="width:100%;"></div>
                 <button @click="transformAnonToUser(user.id)" class="action-btn validate-btn" 
                         :disabled="!createAnonForm.first_name || !createAnonForm.last_name || !createAnonForm.email || isLoading">
                    Créer Profil
                 </button>
               </div>
            </div>
         </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.text-link { color: inherit; text-decoration: none; }
.text-link:hover strong { color: var(--zenika-red); text-decoration: underline; }

.admin-wrapper { max-width: 1100px; margin: 0 auto; padding: 2rem; }

.tabs-container { display: flex; gap: 1rem; margin-top: 1rem; }
.tab-btn { background: rgba(255, 255, 255, 0.5); border: 1px solid rgba(255, 255, 255, 0.4); padding: 0.75rem 1.5rem; border-radius: 12px; cursor: pointer; font-weight: 600; color: #64748b; transition: all 0.2s; backdrop-filter: blur(10px); }
.tab-btn:hover { background: rgba(255, 255, 255, 0.8); color: #1e293b; }
.tab-btn.active { background: white; color: var(--zenika-red); border-color: white; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); }
.header-banner { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 20px; padding: 2.5rem; color: white; display: flex; align-items: center; gap: 1.5rem; margin-bottom: 2.5rem; box-shadow: 0 10px 40px rgba(15, 23, 42, 0.2); position: relative; overflow: hidden; }
.banner-icon { background: rgba(227, 25, 55, 0.2); padding: 1.25rem; border-radius: 16px; color: var(--zenika-red); }
.banner-text h2 { font-size: 1.8rem; font-weight: 700; margin: 0 0 0.5rem 0; }
.banner-text p { color: #94a3b8; margin: 0; font-size: 1.05rem; }
.status-badge { position: absolute; top: 1.5rem; right: 1.5rem; background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 0.5rem 1rem; border-radius: 30px; font-size: 0.85rem; font-weight: 600; display: flex; align-items: center; gap: 6px; border: 1px solid rgba(52, 211, 153, 0.3); }

.glass-panel { background: rgba(255, 255, 255, 0.5); backdrop-filter: blur(20px); border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.4); padding: 2rem; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04); }
.panel-header { margin-bottom: 1.5rem; }
.panel-header h3 { font-size: 1.25rem; font-weight: 700; color: #1e293b; margin: 0;}
.d-flex-between { display: flex; justify-content: space-between; align-items: center; }

.action-btn-secondary { background: white; border: 1px solid #e2e8f0; padding: 0.5rem 1rem; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 8px; }
.action-btn-secondary:hover { background: #f8fafc; }

.empty-state { text-align: center; padding: 3rem; color: #64748b; }
.empty-state p { margin-top: 1rem; font-size: 1.1rem; }

.duplicate-card { background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 2px 10px rgba(0,0,0,0.02); }
.dup-title { font-size: 1.1rem; margin-bottom: 1rem; color: #334155; border-bottom: 1px solid #f1f5f9; padding-bottom: 0.5rem; }

.users-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
.user-item { padding: 1rem; background: #f8fafc; border-radius: 8px; border: 1px solid #f1f5f9; }
.user-info strong { color: #0f172a; font-size: 1.05rem; }
.text-xs { font-size: 0.8rem; }
.text-muted { color: #64748b; line-height: 1.5; display: inline-block; margin-top: 0.25rem; }

.merge-controls { display: flex; gap: 1.5rem; align-items: flex-end; background: #fff5f5; padding: 1.25rem; border-radius: 8px; border: 1px solid rgba(227, 25, 55, 0.1); }
.control-group { display: flex; flex-direction: column; gap: 0.5rem; flex: 1; }
.control-group label { font-size: 0.85rem; font-weight: 600; color: #475569; }
.form-select { padding: 0.6rem; border-radius: 6px; border: 1px solid #cbd5e1; outline: none; background: white; }
.form-select:focus { border-color: var(--zenika-red); box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1); }

.action-btn { border: none; padding: 0.75rem 1.5rem; border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }
.validate-btn { background: var(--zenika-red); color: white; box-shadow: 0 4px 12px rgba(227, 25, 55, 0.2); height: 42px; }
.validate-btn:hover:not(:disabled) { background: #c3132e; transform: translateY(-1px); }
.validate-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.error-panel { margin-top: 2rem; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); padding: 1.5rem; border-radius: 12px; color: #b91c1c; display: flex; gap: 10px; }
.success-panel { margin-top: 2rem; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); padding: 1.5rem; border-radius: 12px; color: #059669; display: flex; align-items: center; gap: 15px; }

.spin { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }
.fade-in { animation: fadeIn 0.4s ease forwards; }
.fade-in-up { animation: fadeInUp 0.5s ease forwards; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
.mt-4 { margin-top: 2rem; }
</style>
