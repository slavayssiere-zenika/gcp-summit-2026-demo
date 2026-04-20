<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
import { 
  User as UserIcon, 
  Mail, 
  Award, 
  CheckCircle2, 
  Briefcase, 
  X, 
  ExternalLink,
  Loader2,
  Calendar,
  ShieldCheck
} from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import CompetencyEvaluationPanel from './CompetencyEvaluationPanel.vue'


const props = defineProps<{
  userId: number
}>()

const emit = defineEmits(['close'])
const router = useRouter()

const user = ref<any>(null)
const competencies = ref<any[]>([])
const missions = ref<any[]>([])
const loading = ref(true)
const error = ref('')

const fetchData = async () => {
  if (!props.userId) return
  loading.value = true
  error.value = ''
  
  try {
    // 1. Identity
    const userRes = await axios.get(`/api/users/${props.userId}`)
    user.value = userRes.data

    // 2. Competencies
    try {
      const compRes = await axios.get(`/api/competencies/user/${props.userId}`)
      competencies.value = compRes.data || []
    } catch(e) {
      console.warn('Could not fetch competencies')
    }

    // 3. Missions
    try {
      const missionRes = await axios.get(`/api/cv/user/${props.userId}/missions`)
      missions.value = (missionRes.data.missions || []).slice(0, 3) // Limit to 3 for compact view
    } catch(e) {
      console.warn('Could not fetch missions')
    }
  } catch (err: any) {
    console.error('Error fetching consultant profile:', err)
    error.value = "Impossible de charger les données du consultant."
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
watch(() => props.userId, fetchData)

const goToProfile = () => {
  router.push(`/profile/${props.userId}`)
}
</script>

<template>
  <div class="consultant-profile-overlay fade-in">
    <div class="profile-card glass-morphism">
      <button class="close-btn" @click="emit('close')" aria-label="Fermer">
        <X size="20" />
      </button>

      <div v-if="loading" class="loading-state">
        <Loader2 class="spin" size="32" />
        <p>Génération de l'aperçu...</p>
      </div>

      <div v-else-if="error" class="error-state">
        <p>{{ error }}</p>
        <button @click="emit('close')" class="action-btn secondary">Fermer</button>
      </div>

      <template v-else-if="user">
        <div class="profile-header">
          <div class="avatar-container">
            <div class="avatar-glow"></div>
            <div class="avatar-inner">
              <UserIcon size="32" />
            </div>
            <div class="status-indicator" :class="{ active: user.is_active }"></div>
          </div>
          <div class="identity">
            <h2>{{ user.full_name || user.username }}</h2>
            <div class="identity-meta">
              <span class="email"><Mail size="14" /> {{ user.email }}</span>
              <span v-if="user.is_anonymous" class="badge-anon">Anonyme</span>
            </div>
          </div>
        </div>

        <div class="profile-content">
          <!-- Technos Section -->
          <div class="section">
            <div class="section-title">
              <Award size="18" class="icon-red" />
              <h3>Expertise Technique (RAG)</h3>
            </div>
            <div v-if="competencies.length === 0" class="empty-compact">
              Aucune expertise cartographiée.
            </div>
            <div v-else class="skills-grid">
              <span v-for="skill in competencies.slice(0, 8)" :key="skill.id" class="skill-tag-mini">
                <CheckCircle2 size="12" class="icon-green" />
                {{ skill.name }}
              </span>
              <span v-if="competencies.length > 8" class="more-tag">+ {{ competencies.length - 8 }}</span>
            </div>
          </div>

          <!-- Missions Section -->
          <div class="section">
            <div class="section-title">
              <Briefcase size="18" class="icon-red" />
              <h3>Parcours Récent</h3>
            </div>
            <div v-if="missions.length === 0" class="empty-compact">
              Historique de missions non disponible.
            </div>
            <div v-else class="missions-mini-list">
              <div v-for="(mission, index) in missions" :key="index" class="mission-mini-item">
                <div class="m-header">
                  <strong>{{ mission.title }}</strong>
                  <span class="m-company">{{ mission.company || 'Zenika' }}</span>
                </div>
                <p class="m-desc">{{ mission.description }}</p>
                <div class="m-tags" v-if="mission.competencies">
                  <span v-for="s in mission.competencies.slice(0, 3)" :key="s" class="m-tag">{{ s }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Evaluations Section (Admin — lecture seule) -->
        <div class="section eval-section-admin">
          <div class="section-title">
            <ShieldCheck size="18" class="icon-red" />
            <h3>Évaluations des compétences</h3>
          </div>
          <CompetencyEvaluationPanel :userId="props.userId" :readonly="true" />
        </div>

        <div class="profile-footer">
          <button @click="goToProfile" class="action-btn primary">
            <ExternalLink size="16" />
            Voir le profil complet
          </button>
          <button @click="emit('close')" class="action-btn secondary">Fermer</button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.consultant-profile-overlay {
  margin-bottom: 2rem;
  width: 100%;
  animation: slideDown 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.profile-card {
  position: relative;
  border-radius: 20px;
  overflow: hidden;
  padding: 2rem;
  border: 1px solid rgba(227, 25, 55, 0.15);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.08);
  min-height: 200px;
}

.glass-morphism {
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(20px);
}

.close-btn {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: rgba(0,0,0,0.05);
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  color: #666;
  z-index: 10;
}
.close-btn:hover {
  background: var(--zenika-red);
  color: white;
  transform: rotate(90deg);
}

.profile-header {
  display: flex;
  gap: 1.5rem;
  align-items: center;
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid rgba(0,0,0,0.05);
}

.avatar-container {
  position: relative;
  width: 64px;
  height: 64px;
}

.avatar-glow {
  position: absolute;
  top: -4px; right: -4px; bottom: -4px; left: -4px;
  background: linear-gradient(135deg, var(--zenika-red), #ff6b6b);
  border-radius: 50%;
  opacity: 0.15;
  filter: blur(4px);
}

.avatar-inner {
  position: relative;
  width: 100%;
  height: 100%;
  background: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--zenika-red);
  border: 2px solid white;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  z-index: 2;
}

.status-indicator {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #cbd5e1;
  border: 2px solid white;
  z-index: 3;
}
.status-indicator.active {
  background: #10b981;
}

.identity h2 {
  font-size: 1.6rem;
  font-weight: 800;
  margin-bottom: 0.25rem;
  letter-spacing: -0.5px;
}

.identity-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.email {
  font-size: 0.9rem;
  color: #666;
  display: flex;
  align-items: center;
  gap: 6px;
}

.badge-anon {
  font-size: 0.7rem;
  background: #fff7ed;
  color: #f97316;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 700;
  text-transform: uppercase;
}

.profile-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.profile-columns {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 2.5rem;
}

@media (max-width: 768px) {
  .profile-columns { grid-template-columns: 1fr; gap: 1.5rem; }
}

.eval-section-admin {
  border-top: 1px solid rgba(0,0,0,0.06);
  padding-top: 1.5rem;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 1.25rem;
}

.section-title h3 {
  font-size: 1rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #333;
}

.icon-red { color: var(--zenika-red); }
.icon-green { color: #10b981; }

.skills-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.skill-tag-mini {
  background: white;
  border: 1px solid rgba(0,0,0,0.05);
  padding: 6px 12px;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #444;
}

.more-tag {
  font-size: 0.8rem;
  color: #666;
  padding: 6px;
  font-weight: 600;
}

.missions-mini-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.mission-mini-item {
  background: rgba(255,255,255,0.5);
  padding: 1rem;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.03);
}

.m-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.m-header strong { font-size: 0.95rem; color: #333; }

.m-company {
  font-size: 0.7rem;
  background: rgba(227, 25, 55, 0.08);
  color: var(--zenika-red);
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 700;
}

.m-desc {
  font-size: 0.85rem;
  color: #666;
  line-height: 1.4;
  margin-bottom: 0.5rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.m-tags {
  display: flex;
  gap: 6px;
}

.m-tag {
  font-size: 0.7rem;
  color: #888;
  background: white;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid #f0f0f0;
}

.empty-compact {
  font-style: italic;
  color: #999;
  font-size: 0.9rem;
  padding: 1rem;
  background: rgba(0,0,0,0.02);
  border-radius: 8px;
  text-align: center;
}

.profile-footer {
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid rgba(0,0,0,0.05);
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 10px;
  font-weight: 700;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.action-btn.primary {
  background: var(--zenika-red);
  color: white;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.2);
}
.action-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(227, 25, 55, 0.3);
}

.action-btn.secondary {
  background: rgba(0,0,0,0.05);
  color: #444;
}
.action-btn.secondary:hover {
  background: rgba(0,0,0,0.1);
}

.loading-state, .error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 250px;
  color: #666;
  gap: 1rem;
}

.spin { animation: spin 1s linear infinite; color: var(--zenika-red); }

@keyframes spin { 100% { transform: rotate(360deg); } }
@keyframes slideDown { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

</style>
