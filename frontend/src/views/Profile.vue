<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { authService } from '../services/auth'
import { 
  User as UserIcon, 
  Mail, 
  Hash, 
  ShieldCheck, 
  ChevronRight, 
  AlertCircle,
  Clock,
  Fingerprint,
  MessageSquare,
  Calendar,
  XCircle,
  Plus
} from 'lucide-vue-next'
import axios from 'axios'

interface Category {
  id: number
  name: string
  description: string
}

const categories = ref<Category[]>([])
const isLoadingCategories = ref(true)
const error = ref<string | null>(null)

const fetchCategories = async () => {
  try {
    const response = await axios.get('/api/items/categories')
    categories.value = response.data.items || []
  } catch (err) {
    console.error('Failed to fetch categories:', err)
    error.value = "Impossible de récupérer les noms des catégories."
  } finally {
    isLoadingCategories.value = false
  }
}

const getCategoryName = (id: number) => {
  const cat = categories.value.find(c => c.id === id)
  return cat ? cat.name : `Catégorie #${id}`
}

const user = authService.state.user
const jwtToken = ref(localStorage.getItem('access_token') || 'Token introuvable')

const personalPrompt = ref('')
const isSavingPrompt = ref(false)
const promptSaveSuccess = ref(false)
const promptSaveError = ref(false)

const fetchPersonalPrompt = async () => {
  try {
    // using cookies for auth, proxy passes it, or send Bearer explicitly
    const token = localStorage.getItem('access_token')
    const response = await axios.get('/api/prompts/user/me', {
       headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    personalPrompt.value = response.data.value || ''
  } catch (err) {
    console.error('Failed to fetch personal prompt:', err)
  }
}

const savePersonalPrompt = async () => {
  isSavingPrompt.value = true
  promptSaveSuccess.value = false
  promptSaveError.value = false
  try {
    const token = localStorage.getItem('access_token')
    await axios.put('/api/prompts/user/me', { value: personalPrompt.value }, {
       headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    promptSaveSuccess.value = true
    setTimeout(() => promptSaveSuccess.value = false, 3000)
  } catch (err) {
    console.error('Failed to save personal prompt:', err)
    promptSaveError.value = true
    setTimeout(() => promptSaveError.value = false, 3000)
  } finally {
    isSavingPrompt.value = false
  }
}

const unavailabilityPeriods = ref<any[]>([])
const newPeriod = ref({ start_date: '', end_date: '', type: 'full', reason: 'client' })
const isSavingAvailability = ref(false)

const loadAvailability = () => {
  if (user && user.unavailability_periods) {
    unavailabilityPeriods.value = [...user.unavailability_periods]
  }
}

const addAvailability = async () => {
  if (!newPeriod.value.start_date || !newPeriod.value.end_date) return;
  const updatedPeriods = [...unavailabilityPeriods.value, {...newPeriod.value}]
  try {
    isSavingAvailability.value = true
    const token = localStorage.getItem('access_token')
    await axios.put(`/api/users/${user?.id}`, { 
        unavailability_periods: updatedPeriods 
    }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    unavailabilityPeriods.value = updatedPeriods
    newPeriod.value = { start_date: '', end_date: '', type: 'full', reason: 'client' }
  } catch(e) {
      console.error('Failed saving availability', e)
  } finally {
      isSavingAvailability.value = false
  }
}

const removeAvailability = async (index: number) => {
    const updatedPeriods = [...unavailabilityPeriods.value]
    updatedPeriods.splice(index, 1)
    try {
        const token = localStorage.getItem('access_token')
        await axios.put(`/api/users/${user?.id}`, { 
            unavailability_periods: updatedPeriods 
        }, {
            headers: token ? { Authorization: `Bearer ${token}` } : {}
        })
        unavailabilityPeriods.value = updatedPeriods
    } catch(e) { console.error(e) }
}

onMounted(() => {
  fetchCategories()
  fetchPersonalPrompt()
  loadAvailability()
})
</script>

<template>
  <div class="profile-container">
    <header class="profile-header">
      <div class="header-content">
        <h1>Mon Profil</h1>
        <p>Gérez vos informations et consultez vos accès</p>
      </div>
      <div class="user-badge" v-if="user?.is_active">
        <ShieldCheck size="16" />
        Compte Actif
      </div>
      <div v-if="user?.picture_url" class="avatar-container">
        <img :src="user.picture_url" alt="Avatar" class="avatar-img" />
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
            <div class="value">{{ user?.full_name }}</div>
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
          <h2>Mes Autorisations</h2>
        </div>
        
        <div class="categories-section">
          <p class="section-desc">Vous avez accès aux catégories d'objets suivantes :</p>
          
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
            <p>Aucune catégorie spécifique n'est assignée à votre profil.</p>
          </div>
          
          <div v-if="error" class="error-toast">
            {{ error }}
          </div>
        </div>
      </section>

      <!-- Availability Card -->
      <section class="profile-card availability-card">
        <div class="card-header">
          <Calendar class="icon" />
          <h2>Mes Indisponibilités</h2>
        </div>
        
        <div class="availability-section">
          <p class="section-desc">Déclarez vos périodes d'indisponibilités calendaires (vacances, staffé chez un client).</p>
          
          <div class="availability-list">
            <div v-for="(period, idx) in unavailabilityPeriods" :key="idx" class="availability-item">
              <div class="period-info">
                <strong>{{ period.start_date }}</strong> au <strong>{{ period.end_date }}</strong>
                <span class="badge type">{{ period.type === 'full' ? 'Journée complète' : period.type }}</span>
                <span class="badge reason">{{ period.reason }}</span>
              </div>
              <button @click="removeAvailability(idx)" class="btn-remove" title="Supprimer">
                <XCircle size="18" />
              </button>
            </div>
          </div>

          <div class="add-availability-form">
            <div class="form-row">
              <input type="date" v-model="newPeriod.start_date" class="form-input" />
              <input type="date" v-model="newPeriod.end_date" class="form-input" />
            </div>
            <div class="form-row">
              <select v-model="newPeriod.type" class="form-input">
                <option value="full">Journée</option>
                <option value="am">Matin</option>
                <option value="pm">Après-midi</option>
              </select>
              <select v-model="newPeriod.reason" class="form-input">
                <option value="client">Client</option>
                <option value="vacances">Vacances</option>
                <option value="formation">Formation</option>
              </select>
              <button @click="addAvailability" :disabled="isSavingAvailability" class="btn-add">
                <Plus size="18" /> Ajouter
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Personal Prompt Card -->
      <section class="profile-card prompt-card">
        <div class="card-header">
          <MessageSquare class="icon" />
          <h2>Instructions Personnelles</h2>
        </div>
        
        <div class="prompt-section">
          <p class="section-desc">Définissez vos instructions personnelles qui seront injectées dans le comportement de l'Agent lorsque vous interagirez avec lui :</p>
          
          <textarea 
            v-model="personalPrompt" 
            placeholder="Ex: Réponds-moi toujours en utilisant un ton très professionnel, et n'oublie pas de préciser mes compétences Cloud lors de l'analyse..."
            class="prompt-textarea"
            rows="6"
          ></textarea>
          
          <div class="prompt-actions">
            <button @click="savePersonalPrompt" :disabled="isSavingPrompt" class="save-btn">
              {{ isSavingPrompt ? 'Enregistrement...' : 'Sauvegarder' }}
            </button>
            <span v-if="promptSaveSuccess" class="toast-success">Instructions sauvegardées !</span>
            <span v-if="promptSaveError" class="toast-error">Erreur lors de la sauvegarde.</span>
          </div>
        </div>
      </section>
      
      <!-- JWT Token Card -->
      <section class="profile-card jwt-card">
        <div class="card-header">
          <ShieldCheck class="icon token-icon" />
          <h2>Token d'Authentification JWT</h2>
        </div>
        <div class="jwt-content">
          <p class="section-desc">Ce jeton cryptographique vous identifie pour votre session active :</p>
          <div class="jwt-box">
             {{ jwtToken }}
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.profile-container {
  max-width: 1000px;
  margin: 0 auto;
  animation: fadeIn 0.5s ease-out;
}

.avatar-container {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
  margin-right: 1.5rem;
}

.avatar-img {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  border: 2px solid white;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  object-fit: cover;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
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
  background: #ecfdf5;
  color: #059669;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-weight: 600;
  font-size: 0.875rem;
  border: 1px solid #d1fae5;
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
  items-center: center;
  text-align: center;
  gap: 1rem;
  padding: 2rem;
  background: #fafafa;
  border-radius: 16px;
  color: #999;
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

/* JWT Custom Styles */
.jwt-card {
  grid-column: 1 / -1;
}

.token-icon {
  color: #9d00ff !important;
}

.jwt-content {
  padding: 1.5rem;
}

.jwt-box {
  background-color: #1a1a1a;
  color: #00ff88;
  padding: 1rem;
  border-radius: 8px;
  font-family: monospace;
  font-size: 0.85rem;
  word-break: break-all;
  border: 1px dashed rgba(255, 255, 255, 0.2);
}

/* Availability Card Styles */
.availability-card { grid-column: 1 / -1; }
.availability-list {
  display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.5rem;
}
.availability-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0.75rem 1rem; background: #f8f9fa; border: 1px solid #eee; border-radius: 8px;
}
.period-info { display: flex; align-items: center; gap: 0.75rem; font-size: 0.9rem; }
.badge { padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
.badge.type { background: #e0f2fe; color: #0369a1; }
.badge.reason { background: #fef08a; color: #854d0e; }
.btn-remove { background: none; border: none; color: #ef4444; cursor: pointer; display: flex; align-items: center; padding: 0; }
.btn-remove:hover { color: #dc2626; }
.add-availability-form { display: flex; flex-direction: column; gap: 0.75rem; background: #fafafa; padding: 1rem; border-radius: 8px; border: 1px dashed #ccc; }
.form-row { display: flex; gap: 0.75rem; }
.form-input { padding: 0.5rem; border: 1px solid #ddd; border-radius: 6px; flex: 1; font-family: inherit; }
.btn-add { background: var(--zenika-red); color: white; border: none; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 0.5rem; font-weight: 600; transition: transform 0.1s; }
.btn-add:hover:not(:disabled) { transform: translateY(-1px); }
.btn-add:disabled { opacity: 0.7; }

/* Prompt Card Styles */
.prompt-card {
  grid-column: 1 / -1;
}

.prompt-textarea {
  width: 100%;
  padding: 1rem;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  font-family: inherit;
  font-size: 0.95rem;
  line-height: 1.5;
  resize: vertical;
  transition: border-color 0.2s, box-shadow 0.2s;
  margin-bottom: 1rem;
}

.prompt-textarea:focus {
  outline: none;
  border-color: var(--zenika-red);
  box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1);
}

.prompt-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.save-btn {
  background-color: var(--zenika-red);
  color: white;
  border: none;
  padding: 0.6rem 1.5rem;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s, transform 0.1s;
}

.save-btn:hover:not(:disabled) {
  background-color: #c2152f;
  transform: translateY(-1px);
}

.save-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.toast-success {
  color: #059669;
  font-size: 0.9rem;
  font-weight: 500;
  animation: fadeIn 0.3s;
}

.toast-error {
  color: #dc2626;
  font-size: 0.9rem;
  font-weight: 500;
  animation: fadeIn 0.3s;
}

@media (max-width: 768px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
}
</style>
