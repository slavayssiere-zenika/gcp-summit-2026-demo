<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { Briefcase, Plus, Users, Loader2 } from 'lucide-vue-next'
import { useHead } from '@vueuse/head'
import { useRouter } from 'vue-router'

const router = useRouter()
const missions = ref<any[]>([])
const loading = ref(true)

useHead({ title: 'Fiches Missions - Zenika Console' })

const fetchMissions = async () => {
  try {
    const response = await axios.get('/api/missions/missions')
    missions.value = response.data
  } catch (error) {
    console.error('Erreur chargement missions:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchMissions()
})

const viewMission = (id: number) => {
  router.push(`/missions/${id}`)
}
const newMission = () => {
  router.push(`/missions/new`)
}
</script>

<template>
  <div class="missions-page">
    <div class="page-header">
      <div class="title-section">
        <Briefcase class="title-icon" size="28" />
        <div>
          <h1>Hub Missions (Staffing)</h1>
          <p>Supervisez les appels d'offres et les propositions d'équipes de l'agent IA.</p>
        </div>
      </div>
      <button @click="newMission" class="action-btn">
        <Plus size="18" /> Nouvelle Mission
      </button>
    </div>

    <div v-if="loading" class="loading-state">
      <Loader2 class="spin" size="32" />
      <p>Chargement des missions...</p>
    </div>

    <div v-else-if="missions.length === 0" class="empty-state">
      <Briefcase size="48" class="empty-icon" />
      <h3>Aucune mission</h3>
      <p>Créez une nouvelle fiche mission pour l'analyser.</p>
    </div>

    <div v-else class="missions-grid">
      <div v-for="mission in missions" :key="mission.id" class="mission-card" @click="viewMission(mission.id)">
        <div class="card-header">
          <h3>{{ mission.title }}</h3>
        </div>
        <div class="card-body">
          <p class="desc">{{ mission.description.length > 100 ? mission.description.substring(0, 100) + '...' : mission.description }}</p>
          <div class="skills">
            <span v-for="skill in (mission.extracted_competencies || []).slice(0, 3)" :key="skill" class="skill-tag">{{ skill }}</span>
            <span v-if="(mission.extracted_competencies || []).length > 3" class="skill-tag extra">+{{ mission.extracted_competencies.length - 3 }}</span>
          </div>
          <div class="team-summary">
            <Users size="16" /> {{ (mission.proposed_team || []).filter((m: any) => m.user_id !== 0).length }} consultants proposés
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.missions-page {
  animation: fadeIn 0.4s ease;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  background: white;
  padding: 1.5rem 2rem;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}
.title-section {
  display: flex;
  align-items: center;
  gap: 1rem;
}
.title-icon {
  color: var(--zenika-red);
  background: rgba(227, 25, 55, 0.1);
  padding: 8px;
  border-radius: 12px;
  width: 48px;
  height: 48px;
}
h1 { font-size: 1.5rem; font-weight: 700; color: #1a1a1a; margin-bottom: 4px; }
p { color: #666; font-size: 0.95rem; }

.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.action-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.2);
}

.missions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
}

.mission-card {
  background: white;
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}
.mission-card:hover {
  border-color: rgba(227, 25, 55, 0.3);
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.08);
}
.card-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 1rem;
}
.desc {
  color: #666;
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 1rem;
}
.skills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 1rem;
}
.skill-tag {
  background: rgba(0,0,0,0.05);
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 0.8rem;
  color: #444;
}
.skill-tag.extra {
  background: rgba(227, 25, 55, 0.1);
  color: var(--zenika-red);
  font-weight: 600;
}
.team-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #666;
  font-size: 0.85rem;
  padding-top: 1rem;
  border-top: 1px solid #eee;
}

.loading-state, .empty-state {
  text-align: center;
  padding: 4rem 2rem;
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}
.spin { animation: spin 1s linear infinite; color: var(--zenika-red); margin-bottom: 1rem; }
.empty-icon { color: #ccc; margin-bottom: 1rem; }
@keyframes spin { 100% { transform: rotate(360deg); } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>
