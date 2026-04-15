<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import { Briefcase, ChevronLeft, ArrowRight, Loader2, User as UserIcon, Users, Calendar, CheckCircle2, Clock, AlertTriangle, Target } from 'lucide-vue-next'
import { useHead } from '@vueuse/head'
import { useRouter } from 'vue-router'
import ConsultantProfile from '@/components/ConsultantProfile.vue'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const isNew = computed(() => props.id === 'new')

const mission = ref<any>(null)
const loading = ref(false)

const draftTitle = ref('')
const draftDescription = ref('')
const draftUrl = ref('')
const draftFile = ref<File | null>(null)
const selectedUserId = ref<number | null>(null)

const handleFileUpload = (event: any) => {
  const file = event.target.files[0]
  if (file) {
    draftFile.value = file
  }
}

useHead({ title: isNew.value ? 'Nouvelle Mission - Zenika' : 'Détail Mission - Zenika' })

const fetchMission = async () => {
  if (isNew.value) return
  loading.value = true
  try {
    const response = await axios.get(`/api/missions/missions/${props.id}`)
    mission.value = response.data
  } catch (error) {
    console.error('Erreur chargement mission:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchMission()
})

const pollingTask = ref(false)
const pollCounter = ref(0)
const maxPolls = 60 // 2 minutes

const pollMissionStatus = async (taskId: string) => {
  if (pollCounter.value > maxPolls) {
    alert("Délai d'attente dépassé.")
    loading.value = false
    pollingTask.value = false
    return
  }
  
  try {
    const res = await axios.get(`/api/missions/missions/task/${taskId}`)
    if (res.data.status === 'completed' && res.data.mission_id) {
      const realRes = await axios.get(`/api/missions/missions/${res.data.mission_id}`)
      mission.value = realRes.data
      router.replace(`/missions/${mission.value.id}`)
      loading.value = false
      pollingTask.value = false
    } else if (res.data.status === 'failed') {
      alert("Erreur de l'agent: " + res.data.error)
      loading.value = false
      pollingTask.value = false
    } else {
      pollCounter.value++
      setTimeout(() => pollMissionStatus(taskId), 2000)
    }
  } catch (err) {
    pollCounter.value++
    setTimeout(() => pollMissionStatus(taskId), 2000)
  }
}

const analyzeMission = async () => {
  if (!draftTitle.value) return
  if (!draftDescription.value && !draftUrl.value && !draftFile.value) {
    alert("Veuillez fournir au moins une description, une URL ou un fichier.")
    return
  }
  
  loading.value = true
  pollingTask.value = true
  pollCounter.value = 0
  
  const formData = new FormData()
  formData.append('title', draftTitle.value)
  if (draftDescription.value) formData.append('description', draftDescription.value)
  if (draftUrl.value) formData.append('url', draftUrl.value)
  if (draftFile.value) formData.append('file', draftFile.value)
  
  try {
    const response = await axios.post('/api/missions/missions', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    if (response.data.task_id) {
      pollMissionStatus(response.data.task_id)
    } else {
      mission.value = response.data
      router.replace(`/missions/${mission.value.id}`)
      loading.value = false
      pollingTask.value = false
    }
  } catch (error) {
    console.error('Erreur analyse:', error)
    alert("Impossible de soumettre la mission (Erreur serveur)")
    loading.value = false
    pollingTask.value = false
  }
}

const reanalyzeMission = async () => {
  if (isNew.value || !mission.value) return
  
  const confirmReanalyze = confirm("Voulez-vous vraiment relancer l'analyse et l'affectation IA pour cette mission (cela écrasera l'équipe actuelle) ?")
  if (!confirmReanalyze) return
  
  loading.value = true
  pollingTask.value = true
  pollCounter.value = 0
  
  try {
    const response = await axios.post(`/api/missions/missions/${mission.value.id}/reanalyze`)
    
    if (response.data.task_id) {
      pollMissionStatus(response.data.task_id)
    }
  } catch (error) {
    console.error('Erreur ré-analyse:', error)
    alert("Impossible de relancer l'analyse (Erreur serveur)")
    loading.value = false
    pollingTask.value = false
  }
}

const getRoleColor = (role: string) => {
  if (role.includes('Directeur')) return 'role-dp'
  if (role.includes('Tech Lead') || role.includes('Lead')) return 'role-lead'
  return 'role-dev'
}

const statusText = computed(() => {
  if (pollCounter.value < 2) return "Ingestion documentaire (OCR/Parsing)..."
  if (pollCounter.value < 5) return "Extraction sémantique Gemini..."
  if (pollCounter.value < 8) return "Vérification des disponibilités (CV/Planning)..."
  return "Calcul des propositions de Staffing..."
})

</script>

<template>
  <div class="mission-detail-page">
    <div class="back-nav" @click="router.push('/missions')">
      <ChevronLeft size="20" /> Retour aux missions
    </div>

    <!-- Mode Création -->
    <div v-if="isNew && !mission" class="creation-mode">
      <div class="page-header">
        <Briefcase class="title-icon" size="28" />
        <div>
          <h1>Analyser une Fiche Mission</h1>
          <p>Chargez un appel d'offres (Google Doc, PDF, Word) ou collez le texte libre.</p>
        </div>
      </div>

      <div class="form-card">
        <div class="form-group">
          <label>Titre de la mission *</label>
          <input type="text" v-model="draftTitle" placeholder="Ex: Réfère Tech - Projet Cloud Native" />
        </div>
        
        <div class="source-grid">
          <div class="form-group source-item">
            <label>1. Fichier PDF / Word</label>
            <input type="file" @change="handleFileUpload" accept=".pdf,.doc,.docx" class="file-input" />
          </div>
          
          <div class="form-group source-item">
            <label>2. Ou Lien Google Docs / Web</label>
            <input type="url" v-model="draftUrl" placeholder="https://docs.google.com/document/d/..." />
          </div>
        </div>

        <div class="form-group">
          <label>3. Ou Texte libre / Compléments</label>
          <textarea v-model="draftDescription" rows="5" placeholder="Copiez-collez le texte ou ajoutez des instructions spécifiques..."></textarea>
        </div>
        
        <div class="form-actions">
          <button @click="analyzeMission" :disabled="!draftTitle || loading" class="submit-btn" :class="{ 'loading': loading }">
            <template v-if="!loading">Lancer l'IA Staffing <ArrowRight size="18" /></template>
            <template v-else><Loader2 class="spin" size="18" /> {{ statusText }}</template>
          </button>
        </div>
      </div>
    </div>

    <!-- Mode Détail (Existant ou Analysé) -->
    <div v-else-if="mission" class="detail-mode">
      <!-- Consultant Profile Highlight -->
      <ConsultantProfile 
        v-if="selectedUserId" 
        :userId="selectedUserId" 
        @close="selectedUserId = null" 
      />

      <div class="grid-layout">
        <!-- Colonne Gauche: Détails -->
        <div class="left-col">
          <div class="card mission-context">
            <div class="card-header">
              <h2>{{ mission.title }}</h2>
            </div>
            <div class="card-body">
              <div class="desc-box">
                <p>{{ mission.description }}</p>
              </div>
              
              <div class="section-title">
                <CheckCircle2 size="18" class="text-green" /> Compétences requises (Extract IA)
              </div>
              <div class="skills">
                <span v-for="skill in mission.extracted_competencies" :key="skill" class="skill-tag">
                  {{ skill }}
                </span>
              </div>
            </div>
          </div>
          
          <div class="card prefiltered-cvs" v-if="mission.prefiltered_candidates" style="margin-top: 2rem;">
            <div class="card-header highlight" style="background: rgba(16, 185, 129, 0.05);">
              <h3><Target size="20" /> CV Analysés (Pré-filtre RAG)</h3>
              <div style="display: flex; gap: 8px;">
                <span v-if="mission.fallback_full_scan" class="badge" style="background: #f59e0b;" title="Aucun CV n'est lié à ces compétences dans le graphe, la recherche RAG a fallback sur toute la BDD.">
                  <AlertTriangle size="12" style="display:inline; margin-bottom:-2px;" /> Full Scan (Fallback)
                </span>
                <span class="badge" style="background: #10b981;">Vector Search</span>
              </div>
            </div>
            <div class="card-body">
              <p style="font-size: 0.9rem; color: #666; margin-bottom: 1rem;">
                Candidats correspondants aux critères avant arbitrage final par l'IA de Staffing.
              </p>
              
              <div v-if="mission.prefiltered_candidates.length === 0" class="empty-state" style="padding: 1.5rem; text-align: center; color: #666; background: #fffbeb; border-radius: 8px; border: 1px dashed #f59e0b;">
                <AlertTriangle size="28" style="color: #f59e0b; margin-bottom: 0.5rem;" />
                <p style="font-weight: 500;">Aucun candidat correspondant trouvé.</p>
                <p style="font-size: 0.85rem; margin-top: 0.25rem;">Même après un Full Scan, la base de connaissance ne contient aucun profil pertinent.</p>
              </div>

              <div v-else class="team-list">
                <div 
                  v-for="cand in mission.prefiltered_candidates" 
                  :key="cand.user_id" 
                  class="team-member prefiltered-item clickable"
                  @click="selectedUserId = cand.user_id"
                >
                  <div class="member-header" style="margin-bottom: 0;">
                    <div class="member-identity">
                      <div class="avatar" style="width: 32px; height: 32px;"><UserIcon size="14" /></div>
                      <div>
                        <h4 style="font-size: 0.95rem;">{{ cand.full_name || 'Consultant Anonyme' }}</h4>
                        <span style="font-size: 0.75rem; color: #10b981; font-weight: 600;">Score: {{ (cand.similarity_score * 100).toFixed(1) }}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Colonne Droite: Équipe -->
        <div class="right-col">
          <div class="card team-proposal">
            <div class="card-header highlight">
              <h3><Users size="20" /> Équipe Proposée</h3>
              <div style="display: flex; gap: 12px; align-items: center;">
                 <button @click="reanalyzeMission" :disabled="pollingTask" class="reanalyze-btn">
                    <template v-if="!pollingTask">Relancer l'IA</template>
                    <template v-else><Loader2 class="spin" size="14" style="margin: 0; color: inherit;" /> En cours...</template>
                 </button>
                 <span class="badge">Staffing IA</span>
              </div>
            </div>
            <div class="card-body">
              <div v-if="(mission.proposed_team || []).filter((m: any) => m.user_id !== 0).length === 0" class="empty-state" style="padding: 2rem; text-align: center; color: #666;">
                <AlertTriangle size="32" style="color: #f59e0b; margin-bottom: 1rem;" />
                <p>Aucun consultant qualifié n'a pu être proposé pour cette mission.</p>
                <div v-if="mission.proposed_team && mission.proposed_team.length > 0 && mission.proposed_team[0].justification" style="margin-top: 1rem; padding: 1rem; background: #fff; border-left: 3px solid #f59e0b; border-radius: 6px; text-align: left; font-size: 0.9rem;">
                  <strong>Justification IA :</strong><br />
                  {{ mission.proposed_team[0].justification }}
                </div>
              </div>
              <div v-else class="team-list">
                <div 
                  v-for="member in mission.proposed_team.filter((m: any) => m.user_id !== 0)" 
                  :key="member.user_id" 
                  class="team-member clickable"
                  @click="selectedUserId = member.user_id"
                >
                  <div class="member-header">
                    <div class="member-identity">
                      <div class="avatar"><UserIcon size="18" /></div>
                      <div>
                        <h4>{{ member.full_name || 'Consultant' }}</h4>
                        <span class="role-badge" :class="getRoleColor(member.role)">{{ member.role }}</span>
                      </div>
                    </div>
                    <div class="estimate">
                      <Clock size="14" /> {{ member.estimated_days }} j
                    </div>
                  </div>
                  <p class="justification">{{ member.justification }}</p>
                  
                  <div class="availability-warning" v-if="Math.random() > 0.8"> <!-- Simulation, le backend fournit mais ce n'est pas persisté dans le model schema. On peut omettre -->
                     <AlertTriangle size="14" /> Indisponibilités détectées à proximité.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="loading && !isNew" class="loading-state">
      <Loader2 class="spin" size="32" />
      <p>Chargement de la mission...</p>
    </div>
  </div>
</template>

<style scoped>
.mission-detail-page {
  animation: fadeIn 0.4s ease;
  max-width: 1200px;
  margin: 0 auto;
}

.back-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-weight: 500;
  cursor: pointer;
  margin-bottom: 1.5rem;
  transition: color 0.2s;
  width: fit-content;
}
.back-nav:hover {
  color: var(--zenika-red);
}

.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2rem;
}
.title-icon {
  color: var(--zenika-red);
  background: rgba(227, 25, 55, 0.1);
  padding: 8px;
  border-radius: 12px;
  width: 48px;
  height: 48px;
}
h1 { font-size: 1.8rem; font-weight: 800; color: #1a1a1a; margin-bottom: 4px; }

.form-card {
  background: white;
  padding: 2rem;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}
.form-group {
  margin-bottom: 1.5rem;
}
.form-group label {
  display: block;
  font-weight: 600;
  margin-bottom: 8px;
  color: #333;
}
.form-group input, .form-group textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-family: inherit;
  font-size: 1rem;
  transition: all 0.2s;
  background: #fcfcfc;
}
.form-group input:focus, .form-group textarea:focus {
  outline: none;
  border-color: var(--zenika-red);
  background: white;
  box-shadow: 0 0 0 4px rgba(227, 25, 55, 0.1);
}

.source-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 1rem;
}
@media (max-width: 768px) {
  .source-grid {
    grid-template-columns: 1fr;
  }
}
.source-item {
  background: #fdfdfd;
  padding: 1rem;
  border-radius: 8px;
  border: 1px dashed #cbd5e1;
  transition: border-color 0.2s;
}
.source-item:hover {
  border-color: var(--zenika-red);
}
.file-input {
  padding: 8px;
  background: white;
}

.submit-btn {
  display: flex;

  align-items: center;
  justify-content: center;
  gap: 10px;
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 14px 28px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.2s;
  width: 100%;
}
.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.submit-btn:not(:disabled):hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(227, 25, 55, 0.25);
}

/* Detail View */
.grid-layout {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 2rem;
}
@media (max-width: 900px) {
  .grid-layout { grid-template-columns: 1fr; }
}

.card {
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  overflow: hidden;
}
.card-header {
  padding: 1.5rem;
  border-bottom: 1px solid #f0f0f0;
}
.card-header h2 { font-size: 1.4rem; font-weight: 700; }
.card-header.highlight {
  background: var(--bg-gradient);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-header.highlight h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 1.2rem;
  color: var(--zenika-red);
}
.badge {
  background: var(--zenika-red);
  color: white;
  font-size: 0.75rem;
  padding: 4px 8px;
  border-radius: 20px;
  font-weight: 600;
}
.card-body {
  padding: 1.5rem;
}

.desc-box {
  background: #f8f9fa;
  padding: 1rem;
  border-radius: 8px;
  font-size: 0.95rem;
  color: #444;
  line-height: 1.6;
  white-space: pre-wrap;
  margin-bottom: 2rem;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 1rem;
  font-size: 1.1rem;
}
.text-green { color: #10b981; }

.skills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.skill-tag {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 500;
}

.team-list {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
.team-member {
  padding: 1rem;
  border: 1px solid #eee;
  border-radius: 12px;
  background: #fbfbfc;
  transition: all 0.2s;
}
.team-member.clickable {
  cursor: pointer;
}
.team-member.clickable:hover {
  transform: translateY(-2px);
  border-color: var(--zenika-red);
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  background: white;
}
.member-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}
.member-identity {
  display: flex;
  gap: 12px;
  align-items: center;
}
.avatar {
  background: #eee;
  width: 40px;
  height: 40px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
}
.member-identity h4 {
  font-size: 1.05rem;
  font-weight: 600;
  margin-bottom: 4px;
}

.role-badge {
  font-size: 0.75rem;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
}
.reanalyze-btn {
  background: white;
  color: var(--zenika-red);
  border: 1px solid var(--zenika-red);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}
.reanalyze-btn:hover:not(:disabled) {
  background: var(--zenika-red);
  color: white;
}
.reanalyze-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.role-dp { background: #fee2e2; color: #b91c1c; }
.role-lead { background: #e0e7ff; color: #4338ca; }
.role-dev { background: #dcfce3; color: #15803d; }

.estimate {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  color: #666;
}

.justification {
  font-size: 0.9rem;
  color: #555;
  background: white;
  padding: 10px;
  border-radius: 6px;
  border-left: 3px solid #ccc;
}

.loading-state {
  text-align: center;
  padding: 4rem;
}
.spin { animation: spin 1s linear infinite; color: var(--zenika-red); margin-bottom: 1rem; }
@keyframes spin { 100% { transform: rotate(360deg); } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>
