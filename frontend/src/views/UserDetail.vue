<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { 
  User as UserIcon, 
  Mail, 
  Hash, 
  ShieldCheck, 
  ChevronRight, 
  AlertCircle,
  Fingerprint,
  ArrowLeft,
  Award,
  CheckCircle2,
  History
} from 'lucide-vue-next'
import axios from 'axios'
import CompetencyEvaluationPanel from '../components/CompetencyEvaluationPanel.vue'

const route = useRoute()
const router = useRouter()

const userId = route.params.id as string

interface User {
  id: number
  username: string
  email: string
  full_name: string
  is_active: boolean
  is_anonymous: boolean
  allowed_category_ids: number[]
}

interface Category {
  id: number
  name: string
  description: string
}

const user = ref<User | null>(null)
const categories = ref<Category[]>([])
const isLoading = ref(true)
const isLoadingCategories = ref(true)
const error = ref<string | null>(null)
const errorCategories = ref<string | null>(null)

const fetchUser = async () => {
  try {
    // /auth routes to /users on the API. So /auth/ID/ gets /users/ID
    const response = await axios.get(`/auth/${userId}`)
    user.value = response.data
  } catch (err: any) {
    console.error('Failed to fetch user:', err)
    error.value = "Impossible de récupérer ce profil utilisateur."
  } finally {
    isLoading.value = false
  }
}

const fetchCategories = async () => {
  try {
    const response = await axios.get('/api/items/categories')
    categories.value = response.data.items || []
  } catch (err) {
    console.error('Failed to fetch categories:', err)
    errorCategories.value = "Impossible de récupérer les noms des catégories."
  } finally {
    isLoadingCategories.value = false
  }
}

const getCategoryName = (id: number) => {
  const cat = categories.value.find(c => c.id === id)
  return cat ? cat.name : `Catégorie #${id}`
}

interface Competency {
  id: number
  name: string
  description: string
}

const competencies = ref<Competency[]>([])
const isLoadingCompetencies = ref(true)
const errorCompetencies = ref<string | null>(null)

const fetchCompetencies = async () => {
  try {
    const response = await axios.get(`/api/competencies/user/${userId}`)
    competencies.value = response.data || []
  } catch (err) {
    console.error('Failed to fetch user competencies:', err)
    errorCompetencies.value = "Impossible de récupérer les compétences RAG."
  } finally {
    isLoadingCompetencies.value = false
  }
}

const cvProfiles = ref<any[]>([])
const importerUser = ref<User | null>(null)
const missions = ref<any[]>([])
const isLoadingMissions = ref(false)

const fetchCVProfile = async () => {
  try {
    const response = await axios.get(`/api/cv/user/${userId}`)
    cvProfiles.value = response.data
    
    // We display the importer based on the most recent CV if it exists
    if (cvProfiles.value && cvProfiles.value.length > 0 && cvProfiles.value[0].imported_by_id) {
      const importerRes = await axios.get(`/auth/${cvProfiles.value[0].imported_by_id}`)
      importerUser.value = importerRes.data
    }
  } catch (err) {
    console.warn("No CV profile found for this user.")
  }
}

const fetchMissions = async () => {
  isLoadingMissions.value = true
  try {
    const response = await axios.get(`/api/cv/user/${userId}/missions`)
    missions.value = response.data.missions || []
  } catch (err) {
    console.warn("Missions not found or error fetching them.")
  } finally {
    isLoadingMissions.value = false
  }
}

const isMerging = ref(false)
const mergeSearchQuery = ref('')
const mergeSearchResults = ref<User[]>([])
const isSearchingMerge = ref(false)
const selectedTargetId = ref<number | null>(null)

const searchMergeUsers = async () => {
  if (mergeSearchQuery.value.length < 2) return
  isSearchingMerge.value = true
  try {
    const res = await axios.get('/auth/search', { params: { query: mergeSearchQuery.value, limit: 5 } })
    // Only show non-anonymous, active users? Or any user but the current one
    mergeSearchResults.value = (res.data.items || []).filter((u: User) => u.id !== user.value?.id && !u.is_anonymous)
  } catch (err) {
    console.error('Search failed:', err)
  } finally {
    isSearchingMerge.value = false
  }
}

const confirmMerge = async () => {
  if (!selectedTargetId.value || !user.value) return
  if (!confirm('Êtes-vous sûr de vouloir rattacher ce profil anonyme ? Toutes les données seront fusionnées.')) return
  
  isLoading.value = true
  try {
    await axios.post('/auth/merge', {
      source_id: user.value.id,
      target_id: selectedTargetId.value
    })
    // Redirect to the target user's profile after merge
    router.push({ name: 'user-detail', params: { id: selectedTargetId.value.toString() } })
  } catch (err: any) {
    console.error('Merge failed:', err)
    error.value = "Échec de la fusion des profils."
    isLoading.value = false
  }
}

onMounted(() => {
  fetchUser()
  fetchCategories()
  fetchCompetencies()
  fetchCVProfile()
  fetchMissions()
})
</script>

<template>
  <div class="profile-container">
    <div class="back-link clickable" @click="router.back()">
      <ArrowLeft size="18" /> Retour à la recherche
    </div>
    
    <div v-if="isLoading" class="loading-state main-loader">
      <div class="spinner"></div>
      <span>Chargement du profil...</span>
    </div>

    <div v-else-if="error" class="empty-state error-main">
      <AlertCircle size="32" />
      <h2>Erreur</h2>
      <p>{{ error }}</p>
    </div>

    <template v-else>
      <header class="profile-header">
        <div class="header-content">
          <h1>Profil de {{ user?.full_name || user?.username }}</h1>
          <p v-if="user?.is_anonymous">Ce profil est actuellement <strong>anonyme</strong> (trigramme).</p>
          <p v-else>Consultation d'un profil tiers</p>
        </div>
        <div class="badges-row">
           <div v-if="user?.is_anonymous" class="user-badge anonymous">
            <Fingerprint size="16" />
            Profil Anonyme
          </div>
          <div class="user-badge" :class="user?.is_active ? 'active' : 'inactive'">
            <ShieldCheck size="16" />
            {{ user?.is_active ? 'Compte Actif' : 'Compte Inactif' }}
          </div>
        </div>
      </header>

      <div v-if="user?.is_anonymous" class="merge-alert">
         <div class="alert-content">
            <AlertCircle class="alert-icon" />
            <div>
               <h3>Action Requise : Profil Anonyme détecté</h3>
               <p>Ce profil a été importé anonymement. Vous devez le rattacher à un collaborateur réel pour finaliser son intégration.</p>
            </div>
         </div>
         <button v-if="!isMerging" @click="isMerging = true" class="action-btn-primary">
            Désanonymiser ce profil
         </button>
         
         <div v-if="isMerging" class="merge-form fade-in">
            <div class="search-box">
               <input 
                  type="text" 
                  v-model="mergeSearchQuery" 
                  @input="searchMergeUsers" 
                  placeholder="Rechercher le collaborateur réel (nom, email...)"
                  class="search-input"
               />
               <div v-if="isSearchingMerge" class="spinner small"></div>
            </div>
            
            <div v-if="mergeSearchResults.length > 0" class="results-list">
               <div 
                  v-for="res in mergeSearchResults" 
                  :key="res.id" 
                  class="result-item"
                  :class="{ selected: selectedTargetId === res.id }"
                  @click="selectedTargetId = res.id"
               >
                  <div class="res-info">
                     <strong>{{ res.full_name }}</strong>
                     <span>{{ res.email }}</span>
                  </div>
                  <CheckCircle2 v-if="selectedTargetId === res.id" size="18" />
               </div>
            </div>
            
            <div class="form-actions">
               <button @click="isMerging = false" class="action-btn-secondary">Annuler</button>
               <button 
                  @click="confirmMerge" 
                  class="action-btn-primary" 
                  :disabled="!selectedTargetId"
               >
                  Confirmer le rattachement (Merge)
               </button>
            </div>
         </div>
      </div>

      <div class="profile-grid">
        <!-- User Info Card -->
        <section class="profile-card info-card">
          <div class="card-header">
            <UserIcon class="icon" />
            <h2>Informations Personnelles</h2>
          </div>
          
          <div class="info-list">
            <div class="info-item">
              <label><Fingerprint size="14" /> Username</label>
              <div class="value">{{ user?.username }}</div>
            </div>
            
            <div class="info-item">
              <label><UserIcon size="14" /> Nom Complet</label>
              <div class="value">{{ user?.full_name || 'Non renseigné' }}</div>
            </div>
            
            <div class="info-item">
              <label><Mail size="14" /> Email</label>
              <div class="value">{{ user?.email }}</div>
            </div>
            
            <div class="info-item">
              <label><Hash size="14" /> ID Utilisateur</label>
              <div class="value code">#{{ user?.id }}</div>
            </div>

            <div class="info-item" v-if="importerUser" style="margin-top: 1rem; padding-top: 1rem; border-top: 1px dashed #eee;">
              <label><UserIcon size="14" /> Profil Importé Par</label>
              <div class="value">
                <RouterLink :to="{ name: 'user-detail', params: { id: importerUser.id } }" class="importer-link">
                  {{ importerUser.full_name || importerUser.username }}
                </RouterLink>
              </div>
            </div>
            
            <div class="info-item" v-if="cvProfiles && cvProfiles.length > 0" style="margin-top: 1rem; padding-top: 1rem; border-top: 1px dashed #eee;">
              <label><UserIcon size="14" /> Documents Associés (CVs)</label>
              <div class="value" style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.5rem">
                <template v-for="(cv, index) in cvProfiles" :key="index">
                  <a v-if="cv" :href="cv.source_url" target="_blank" class="importer-link" style="font-size: 0.95rem; display: flex; align-items: center; gap: 0.5rem;">
                    Lien Source vers le CV {{ index + 1 }}
                    <span v-if="cv.source_tag" style="background: rgba(227, 25, 55, 0.05); cursor: default; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; text-decoration: none !important;">{{ cv.source_tag }}</span>
                  </a>
                </template>
              </div>
            </div>
          </div>
        </section>

        <!-- Authorizations Card -->
        <section class="profile-card auth-card">
          <div class="card-header">
            <ShieldCheck class="icon" />
            <h2>Autorisations Assignées</h2>
          </div>
          
          <div class="categories-section">
            <p class="section-desc">Cet utilisateur a accès aux catégories d'objets suivantes :</p>
            
            <div v-if="isLoadingCategories" class="loading-state">
              <div class="spinner"></div>
              <span>Chargement des catégories...</span>
            </div>
            
            <div v-else-if="user?.allowed_category_ids && user.allowed_category_ids.length > 0" class="category-tags">
              <div 
                v-for="id in user.allowed_category_ids" 
                :key="id" 
                class="category-tag"
              >
                <ChevronRight size="14" />
                {{ getCategoryName(id) }}
              </div>
            </div>
            
            <div v-else class="empty-state">
              <AlertCircle size="24" />
              <p>Aucune catégorie spécifique n'est assignée à ce profil.</p>
            </div>
            
            <div v-if="errorCategories" class="error-toast">
              {{ errorCategories }}
            </div>
          </div>
        </section>

        <!-- Competencies RAG Card -->
        <section class="profile-card competencies-card">
          <div class="card-header">
            <Award class="icon" />
            <h2>Cartographie des Compétences RAG</h2>
          </div>
          
          <div class="categories-section">
            <p class="section-desc">Expertise technique et concepts reconnus pour ce profil via le pipeline d'IA sur ses CVs :</p>
            
            <div v-if="isLoadingCompetencies" class="loading-state">
              <div class="spinner"></div>
              <span>Connexion avec l'espace latent...</span>
            </div>
            
            <div v-else-if="competencies && competencies.length > 0" class="category-tags">
              <div 
                v-for="skill in competencies" 
                :key="skill ? skill.id : Math.random()" 
                class="category-tag skill-tag"
              >
                <template v-if="skill">
                  <CheckCircle2 size="14" class="skill-check" />
                  {{ skill.name }}
                </template>
              </div>
            </div>
            
            <div v-else class="empty-state">
              <Award size="24" />
              <p>Ce profil n'a pas encore de CV parsé ni de compétences extraites.</p>
            </div>
            
            <div v-if="errorCompetencies" class="error-toast">
              {{ errorCompetencies }}
            </div>
          </div>
        </section>

         <!-- Missions Card -->
        <section class="profile-card missions-card">
          <div class="card-header">
            <History class="icon" />
            <h2>Historique des Missions</h2>
          </div>
          
          <div class="missions-section">
            <div v-if="isLoadingMissions" class="loading-state">
              <div class="spinner"></div>
              <span>Reconstitution du parcours professionnel...</span>
            </div>
            
            <div v-else-if="missions && missions.length > 0" class="missions-list">
              <div v-for="(mission, index) in missions" :key="index" class="mission-item">
                <template v-if="mission">
                  <div class="mission-header">
                    <h3>{{ mission.title }}</h3>
                    <span class="company-tag">{{ mission.company || 'Entreprise Confidentielle' }}</span>
                  </div>
                  <p class="mission-desc">{{ mission.description }}</p>
                  <div class="mission-skills" v-if="mission.competencies && mission.competencies.length > 0">
                    <span v-for="skill in mission.competencies" :key="skill" class="mini-skill-tag">
                      {{ skill }}
                    </span>
                  </div>
                </template>
              </div>
            </div>
            
            <div v-else class="empty-state">
              <History size="24" />
              <p>Aucune mission n'a été extraite de ce profil pour le moment.</p>
            </div>
          </div>
        </section>

        <!-- Évaluations des Compétences (lecture seule) -->
        <section class="profile-card eval-card-ro">
          <div class="card-header">
            <Award class="icon" />
            <h2>Évaluations des Compétences</h2>
          </div>
          <p class="section-desc">Notes Gemini et auto-évaluations du consultant · Vue lecture seule.</p>
          <CompetencyEvaluationPanel :userId="Number(userId)" :readonly="true" />
        </section>

      </div>
    </template>
  </div>
</template>

<style scoped>
.profile-container {
  max-width: 1000px;
  margin: 0 auto;
  animation: fadeIn 0.5s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--zenika-red);
  font-weight: 600;
  margin-bottom: 2rem;
  cursor: pointer;
  transition: opacity 0.2s;
}

.back-link:hover {
  opacity: 0.8;
}

.profile-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 2.5rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #e0e0e0;
}

h1 {
  font-size: 2.25rem;
  font-weight: 800;
  color: #1a1a1a;
  margin-bottom: 0.5rem;
  letter-spacing: -0.5px;
}

.header-content p {
  color: #666;
  font-size: 1.1rem;
}

.user-badge {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-weight: 600;
  font-size: 0.875rem;
  border: 1px solid transparent;
}

.user-badge.active {
  background: #ecfdf5;
  color: #059669;
  border-color: #d1fae5;
}

.user-badge.inactive {
  background: #fef2f2;
  color: #ef4444;
  border-color: #fee2e2;
}

.user-badge.anonymous {
  background: #fff7ed;
  color: #f97316;
  border-color: #ffedd5;
}

.badges-row {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.merge-alert {
  background: linear-gradient(135deg, #fff7ed 0%, #fff 100%);
  border: 1px solid #ffedd5;
  border-radius: 20px;
  padding: 2rem;
  margin-bottom: 2.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  box-shadow: 0 4px 15px rgba(249, 115, 22, 0.05);
}

.alert-content {
  display: flex;
  gap: 1.5rem;
  align-items: flex-start;
}

.alert-icon {
  color: #f97316;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
}

.merge-alert h3 {
  color: #9a3412;
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 0.25rem;
}

.merge-alert p {
  color: #c2410c;
  font-size: 0.95rem;
}

.merge-form {
  padding-top: 1.5rem;
  border-top: 1px solid #ffedd5;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.search-input {
  width: 100%;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  border: 1.5px solid #ffedd5;
  outline: none;
  font-size: 1rem;
  transition: border-color 0.2s;
}

.search-input:focus {
  border-color: #f97316;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 250px;
  overflow-y: auto;
}

.result-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: white;
  border: 1.5px solid #eee;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.result-item:hover {
  border-color: #f97316;
  background: #fff7ed;
}

.result-item.selected {
  border-color: #f97316;
  background: #fff7ed;
  color: #f97316;
}

.res-info {
  display: flex;
  flex-direction: column;
}

.res-info span {
  font-size: 0.85rem;
  color: #666;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  margin-top: 0.5rem;
}

.action-btn-primary {
  background: #f97316;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.2s, background 0.2s;
}

.action-btn-primary:hover:not(:disabled) {
  background: #ea580c;
  transform: translateY(-2px);
}

.action-btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner.small {
  width: 16px;
  height: 16px;
}

.profile-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
}

.eval-card-ro {
  grid-column: 1 / -1;
}

.profile-card {
  background: white;
  border-radius: 24px;
  padding: 2rem;
  box-shadow: 0 10px 25px rgba(0,0,0,0.03);
  border: 1px solid #f0f0f0;
  transition: transform 0.2s;
}

.profile-card:hover {
  transform: translateY(-4px);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2rem;
}

.card-header h2 {
  font-size: 1.25rem;
  font-weight: 700;
  color: #1a1a1a;
}

.card-header .icon {
  color: var(--zenika-red);
  opacity: 0.9;
}

/* Info Items */
.info-list {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.info-item label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  color: #999;
  margin-bottom: 0.5rem;
  letter-spacing: 0.5px;
}

.info-item .value {
  font-size: 1.1rem;
  font-weight: 500;
  color: #1a1a1a;
  padding-left: 0.5rem;
}

.info-item .value.code {
  font-family: 'JetBrains Mono', monospace;
  color: var(--zenika-red);
  background: rgba(227, 25, 55, 0.05);
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 6px;
  font-size: 1rem;
}

/* Categories */
.section-desc {
  color: #666;
  font-size: 0.95rem;
  margin-bottom: 1.5rem;
}

.importer-link {
  color: var(--zenika-red);
  text-decoration: none;
  font-weight: 600;
  transition: opacity 0.2s;
}

.importer-link:hover {
  text-decoration: underline;
}

.category-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.category-tag {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #f8f9fa;
  border: 1.5px solid #eee;
  padding: 0.6rem 1rem;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.9rem;
  color: #444;
  transition: all 0.2s;
}

.category-tag:hover {
  border-color: var(--zenika-red);
  background: #fff5f5;
  color: var(--zenika-red);
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 1rem;
  color: #999;
  font-size: 0.9rem;
}

.main-loader {
  justify-content: center;
  margin-top: 4rem;
  font-size: 1.2rem;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #eee;
  border-top-color: var(--zenika-red);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 1rem;
  padding: 2rem;
  background: #fafafa;
  border-radius: 16px;
  color: #999;
}

.error-main {
  color: #ef4444;
  margin-top: 2rem;
}

.error-main h2 {
  color: #ef4444;
  margin: 0;
}

.error-toast {
  margin-top: 1rem;
  padding: 0.75rem;
  background: #fef2f2;
  color: #ef4444;
  border-radius: 10px;
  font-size: 0.85rem;
  border: 1px solid #fee2e2;
}

.competencies-card {
  grid-column: 1 / -1;
}

.skill-tag {
  background: white;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.skill-check {
  color: var(--zenika-red);
}

/* Missions */
.missions-card {
  grid-column: 1 / -1;
  margin-top: 2rem;
}

.missions-list {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.mission-item {
  padding: 1.5rem;
  background: #fafafa;
  border-radius: 16px;
  border: 1px solid #eee;
  transition: all 0.2s;
}

.mission-item:hover {
  background: white;
  border-color: var(--zenika-red);
  box-shadow: 0 4px 20px rgba(0,0,0,0.05);
}

.mission-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.mission-header h3 {
  font-size: 1.1rem;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0;
}

.company-tag {
  background: rgba(227, 25, 55, 0.05);
  color: var(--zenika-red);
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.mission-desc {
  color: #666;
  font-size: 0.95rem;
  line-height: 1.6;
  margin-bottom: 1.25rem;
}

.mission-skills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.mini-skill-tag {
  background: white;
  border: 1px solid #ddd;
  padding: 2px 10px;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  color: #555;
}

@media (max-width: 768px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
}
</style>
