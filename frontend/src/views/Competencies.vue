<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import CompetencyNode from '../components/CompetencyNode.vue'
import { Network, RefreshCw, User, X, ExternalLink, Users } from 'lucide-vue-next'

const competencies = ref<any[]>([])
const loading = ref(true)
const error = ref('')

// Sidepanel state
const isSidepanelOpen = ref(false)
const selectedCompetency = ref<any>(null)
const associatedUsers = ref<any[]>([])
const totalUserCount = ref(0)
const isLoadingUsers = ref(false)

const onSelectLeaf = async (node: any) => {
  selectedCompetency.value = node
  isSidepanelOpen.value = true
  isLoadingUsers.value = true
  associatedUsers.value = []
  totalUserCount.value = 0
  
  try {
    // 1. Get user IDs from competencies API
    const userIdsRes = await axios.get(`/comp-api/${node.id}/users`)
    const allUserIds = userIdsRes.data || []
    totalUserCount.value = allUserIds.length
    
    if (allUserIds.length > 0) {
      // 2. Limit to 10 for display
      const topIds = allUserIds.slice(0, 10)
      
      // 3. Resolve user details from users API bulk endpoint
      const usersRes = await axios.post(`/users-api/bulk`, topIds)
      associatedUsers.value = usersRes.data || []
    }
  } catch (err) {
    console.error("Failed to fetch associated users", err)
  } finally {
    isLoadingUsers.value = false
  }
}

const closeSidepanel = () => {
  isSidepanelOpen.value = false
}

const fetchCompetencies = async () => {
  loading.value = true
  error.value = ''
  
  try {
    const limit = 50
    const firstRes = await axios.get(`/comp-api/?skip=0&limit=${limit}`)
    let allItems = firstRes.data.items || []
    const total = firstRes.data.total || 0
    
    if (total > limit) {
      const promises = []
      for (let skip = limit; skip < total; skip += limit) {
        promises.push(axios.get(`/comp-api/?skip=${skip}&limit=${limit}`))
      }
      const responses = await Promise.all(promises)
      responses.forEach(res => {
        allItems = allItems.concat(res.data.items || [])
      })
    }
    
    competencies.value = allItems
  } catch (err: any) {
    error.value = "Impossible de charger l'arbre des compétences."
    console.error(err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchCompetencies()
})
</script>

<template>
  <div class="competencies-container fade-in">
    <div class="header-section">
      <div class="title-wrapper">
        <Network class="icon-title" size="32" />
        <h2>Référentiel de Compétences</h2>
      </div>
      <p class="subtitle">Arborescence globale des expertises et technologies de pointe Zenika.</p>
    </div>

    <div class="tree-card glass-panel">
      <div class="card-header">
        <h3>Explorateur Stratégique</h3>
        <button class="icon-btn" @click="fetchCompetencies" :disabled="loading" title="Actualiser l'arbre">
          <RefreshCw size="18" :class="{ 'spin': loading }" />
        </button>
      </div>

      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>Récupération du graphe de compétences...</span>
      </div>

      <div v-else-if="error" class="error-msg">
        {{ error }}
      </div>

      <div v-else-if="competencies.length === 0" class="empty-state">
        Aucune compétence n'est actuellement définie.
      </div>

      <div v-else class="tree-view">
        <CompetencyNode 
          v-for="rootNode in competencies" 
          :key="rootNode.id" 
          :node="rootNode"
          :depth="0"
          @select-leaf="onSelectLeaf"
        />
      </div>
    </div>

    <!-- Sidepanel (Drawer) -->
    <Transition name="slide-panel">
      <div v-if="isSidepanelOpen" class="sidepanel-overlay" @click.self="closeSidepanel">
        <div class="sidepanel-content glass-panel" @click.stop>
          <div class="sidepanel-header">
            <div class="header-main">
               <div class="comp-icon"><Network size="20" /></div>
               <div class="comp-title">
                  <h3>{{ selectedCompetency?.name }}</h3>
                  <div class="side-aliases" v-if="selectedCompetency?.aliases">
                    <span v-for="alias in selectedCompetency.aliases.split(',')" :key="alias" class="side-alias-badge">
                      {{ alias.trim() }}
                    </span>
                  </div>
                  <span class="comp-id">#{{ selectedCompetency?.id }}</span>
               </div>
            </div>
            <button class="close-btn" @click="closeSidepanel">
              <X size="20" />
            </button>
          </div>

          <div class="sidepanel-body">
            <div class="stats-banner">
              <Users size="18" />
              <span>{{ totalUserCount }} consultant(s) concerné(s)</span>
            </div>

            <div v-if="isLoadingUsers" class="fetching-state">
              <div class="pulse-spinner"></div>
              <p>Récupération des profils...</p>
            </div>

            <div v-else-if="associatedUsers.length === 0" class="no-users">
              <User size="32" class="opacity-20" />
              <p>Aucun utilisateur associé à cette compétence pour le moment.</p>
            </div>

            <div v-else class="users-list">
              <p class="list-hint" v-if="totalUserCount > 10">Affichage des 10 profils les plus récents :</p>
              
              <div v-for="user in associatedUsers" :key="user.id" class="user-card">
                <div class="user-avatar">
                   <img v-if="user.picture_url" :src="user.picture_url" :alt="user.full_name">
                   <User v-else size="20" />
                </div>
                <div class="user-info">
                   <span class="user-name">{{ user.full_name }}</span>
                   <span class="user-role">{{ user.role }}</span>
                </div>
                <RouterLink :to="{ name: 'user-detail', params: { id: user.id } }" class="profile-link" title="Voir le profil">
                   <ExternalLink size="16" />
                </RouterLink>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.competencies-container {
  max-width: 1000px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header-section {
  text-align: center;
  margin-bottom: 40px;
}

.title-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 12px;
}

h2 {
  font-size: 36px;
  font-weight: 800;
  color: #1A1A1A;
  letter-spacing: -1px;
}

.icon-title {
  color: #E31937;
}

.subtitle {
  color: #555;
  font-size: 18px;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(227, 25, 55, 0.08);
  overflow: hidden;
}

.tree-card {
  padding: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 30px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(20, 20, 20, 0.6);
}

h3 {
  font-size: 18px;
  font-weight: 600;
  color: #1A1A1A;
  margin: 0;
}

.tree-view {
  padding: 20px 30px 40px 30px;
  min-height: 300px;
}

.loading-state, .empty-state, .error-msg {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: #888;
  text-align: center;
}

.error-msg {
  color: #ff5252;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(227, 25, 55, 0.2);
  border-top-color: #E31937;
  border-radius: 50%;
  animation: spin 1s infinite linear;
  margin-bottom: 16px;
}

.icon-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #ccc;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.icon-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.spin {
  animation: spin 1s infinite linear;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.fade-in {
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Sidepanel Transitions & Styles */
.slide-panel-enter-active, .slide-panel-leave-active {
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.slide-panel-enter-from, .slide-panel-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.sidepanel-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.3);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.sidepanel-content {
  width: 400px;
  max-width: 90vw;
  height: 100%;
  border-left: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 20px 0 0 20px;
  display: flex;
  flex-direction: column;
  animation: slideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

.sidepanel-header {
  padding: 24px 30px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.header-main {
  display: flex;
  align-items: center;
  gap: 12px;
}

.comp-icon {
  background: rgba(227, 25, 55, 0.1);
  color: #E31937;
  padding: 8px;
  border-radius: 8px;
}

.comp-title h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  color: #1e293b;
}

.comp-id {
  font-size: 0.75rem;
  font-family: monospace;
  color: #E31937;
  font-weight: 600;
}

.side-aliases {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 6px 0;
}

.side-alias-badge {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  background: rgba(227, 25, 55, 0.05);
  color: #E31937;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid rgba(227, 25, 55, 0.1);
}

.close-btn {
  background: #f1f5f9;
  border: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #64748b;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #e2e8f0;
  color: #0f172a;
}

.sidepanel-body {
  flex: 1;
  padding: 30px;
  overflow-y: auto;
}

.stats-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #f8fafc;
  padding: 12px 16px;
  border-radius: 12px;
  color: #1e293b;
  font-weight: 600;
  margin-bottom: 24px;
}

.fetching-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  margin-top: 60px;
  color: #64748b;
}

.pulse-spinner {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #E31937;
  animation: pulseScale 1.5s infinite ease-in-out;
}

@keyframes pulseScale {
  0% { transform: scale(0.8); opacity: 0.5; }
  50% { transform: scale(1.1); opacity: 1; }
  100% { transform: scale(0.8); opacity: 0.5; }
}

.no-users {
  text-align: center;
  color: #94a3b8;
  margin-top: 60px;
}

.no-users p {
  margin-top: 12px;
  font-size: 0.95rem;
}

.users-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.list-hint {
  font-size: 0.8rem;
  color: #64748b;
  font-style: italic;
  margin-bottom: 4px;
}

.user-card {
  display: flex;
  align-items: center;
  padding: 12px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  transition: all 0.2s;
}

.user-card:hover {
  border-color: #E31937;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.05);
}

.user-avatar {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  margin-right: 12px;
  color: #94a3b8;
}

.user-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.user-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.user-name {
  font-weight: 600;
  font-size: 0.95rem;
  color: #1e293b;
}

.user-role {
  font-size: 0.75rem;
  color: #64748b;
  text-transform: capitalize;
}

.profile-link {
  color: #94a3b8;
  padding: 8px;
  border-radius: 8px;
  transition: all 0.2s;
}

.profile-link:hover {
  background: #f1f5f9;
  color: #E31937;
}

.opacity-20 { opacity: 0.2; }
</style>

