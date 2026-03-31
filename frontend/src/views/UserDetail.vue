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
  CheckCircle2
} from 'lucide-vue-next'
import axios from 'axios'

const route = useRoute()
const router = useRouter()

const userId = route.params.id as string

interface User {
  id: number
  username: string
  email: string
  full_name: string
  is_active: boolean
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
    const response = await axios.get('/items-api/items/categories')
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
    const response = await axios.get(`/comp-api/competencies/user/${userId}`)
    competencies.value = response.data || []
  } catch (err) {
    console.error('Failed to fetch user competencies:', err)
    errorCompetencies.value = "Impossible de récupérer les compétences RAG."
  } finally {
    isLoadingCompetencies.value = false
  }
}

onMounted(() => {
  fetchUser()
  fetchCategories()
  fetchCompetencies()
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
          <p>Consultation d'un profil tiers</p>
        </div>
        <div class="user-badge" :class="user?.is_active ? 'active' : 'inactive'">
          <ShieldCheck size="16" />
          {{ user?.is_active ? 'Compte Actif' : 'Compte Inactif' }}
        </div>
      </header>

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
                :key="skill.id" 
                class="category-tag skill-tag"
              >
                <CheckCircle2 size="14" class="skill-check" />
                {{ skill.name }}
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

.profile-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
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

@media (max-width: 768px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
}
</style>
