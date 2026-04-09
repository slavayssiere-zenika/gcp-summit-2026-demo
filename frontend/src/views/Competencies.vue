<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import CompetencyNode from '../components/CompetencyNode.vue'
import { Network, RefreshCw } from 'lucide-vue-next'

const competencies = ref<any[]>([])
const loading = ref(true)
const error = ref('')

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
        />
      </div>
    </div>
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
</style>
