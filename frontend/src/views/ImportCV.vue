<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { FileDown, RefreshCw, CheckCircle, AlertCircle, Lock } from 'lucide-vue-next'
import { authService } from '../services/auth'

const cvUrl = ref('')
const loading = ref(false)
const error = ref('')
const successData = ref<any>(null)
const googleClientId = ref('')
const tokenClient = ref<any>(null)

onMounted(async () => {
  try {
    const res = await axios.get('/auth/google/config')
    if (res.data.client_id) {
      googleClientId.value = res.data.client_id
      initGoogleClient()
    }
  } catch (err) {
    console.warn("Impossible de récupérer la configuration Google ID")
  }
})

const initGoogleClient = () => {
  if (!(window as any).google) return;
  tokenClient.value = (window as any).google.accounts.oauth2.initTokenClient({
    client_id: googleClientId.value,
    scope: 'https://www.googleapis.com/auth/documents.readonly https://www.googleapis.com/auth/drive.readonly',
    callback: (response: any) => {
      if (response.error !== undefined) {
        throw (response);
      }
      executeImport(response.access_token);
    },
  });
}

const handlePrivateImport = () => {
  if (!cvUrl.value) {
    error.value = "Veuillez d'abord renseigner le lien du Google Doc.";
    return;
  }
  
  error.value = '';
  
  if (!tokenClient.value && googleClientId.value) {
    initGoogleClient();
  }

  if (!tokenClient.value) {
    if (!googleClientId.value) {
      error.value = "Configuration Google ID manquante. Vérifiez que 'source secrets.sh' a bien été exécuté avant 'docker-compose up'.";
    } else {
      error.value = "Le script d'authentification Google est introuvable (bloqué par un bloqueur de pub ?)";
    }
    return;
  }
  
  loading.value = true;
  tokenClient.value.requestAccessToken();
}

const submitCV = async () => {
  if (!cvUrl.value) return
  await executeImport()
}

const executeImport = async (googleToken?: string) => {
  loading.value = true
  error.value = ''
  successData.value = null

  try {
    const payload: any = { url: cvUrl.value }
    if (googleToken) {
      payload.google_access_token = googleToken
    }
    const response = await axios.post('/api/cv/import', 
      payload,
      { headers: { Authorization: `Bearer ${authService.state.token}` } }
    )
    successData.value = response.data
    cvUrl.value = ''
  } catch (err: any) {
    console.error(err)
    if (err.response?.status === 400 && err.response?.data?.detail?.includes("refusé")) {
      error.value = "Accès refusé. Veuillez utiliser le bouton 'Importer en mode Privé'."
    } else {
      error.value = err.response?.data?.detail || "Erreur lors de l'analyse du CV. Vérifiez le lien."
    }
  } finally {
    loading.value = false
  }
}
</script>


<template>
  <div class="import-wrapper fade-in">
    <div class="header-section">
      <div class="title-wrapper">
        <FileDown class="icon-title" size="32" />
        <h2>Import CV (RAG)</h2>
      </div>
      <p class="subtitle">Scannez un profil via l'Intelligence Artificielle de Google Gemini</p>
    </div>

    <!-- Interface -->
    <div class="reader-card glass-panel">
      <div class="card-header">
        <h3>Analyser un Google Doc</h3>
      </div>

      <div class="card-body">
        <form @submit.prevent="submitCV" class="import-form">
          <div class="form-group">
            <label>Lien Public du Google Doc</label>
            <input 
              v-model="cvUrl" 
              type="url" 
              required
              class="glass-input" 
              placeholder="https://docs.google.com/document/d/.../edit"
            />
            <small class="hint">Assurez-vous que le lien est réglé sur "Tous les utilisateurs disposant du lien".</small>
          </div>
          
          <div class="actions-group">
            <button type="submit" class="submit-btn" :disabled="loading || !cvUrl">
              <RefreshCw v-if="loading" size="18" class="spin" />
              <span v-else>Scanner & Intégrer (Public)</span>
            </button>
            <button type="button" @click="handlePrivateImport" class="submit-btn private-btn" :disabled="loading" title="Autoriser l'accès à ce document privé via Google">
              <Lock size="18" />
              <span>Importer avec mon compte Google</span>
            </button>
          </div>
        </form>

        <div v-if="error" class="alert-box error">
          <AlertCircle size="20" />
          <span>{{ error }}</span>
        </div>

        <div v-if="successData" class="alert-box success">
          <CheckCircle size="24" class="success-icon" />
          <div class="success-content">
            <h4>Analyse Terminée</h4>
            <p>{{ successData.message }}</p>
            <div class="badges">
              <span class="badge user">👤 User ID #{{ successData.user_id }}</span>
              <span class="badge comp">⭐ {{ successData.competencies_assigned }} Compétences Vectorisées</span>
            </div>
            <RouterLink :to="{ name: 'user-detail', params: { id: successData.user_id } }" class="view-btn">
              Voir la fiche du Consultant
            </RouterLink>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<style scoped>
.import-wrapper {
  max-width: 800px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header-section {
  text-align: center;
  margin-bottom: 30px;
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
  color: #1a1a1a;
  letter-spacing: -1px;
}

.icon-title {
  color: #E31937;
}

.subtitle {
  color: #475569;
  font-size: 18px;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 16px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.card-header {
  padding: 20px 30px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  background: rgba(250, 250, 250, 0.9);
}

.card-header h3 {
  font-size: 20px;
  font-weight: 700;
  color: #1A1A1A;
  margin: 0;
}

.card-body {
  padding: 30px;
}

.import-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

label {
  font-weight: 600;
  color: #333;
}

.glass-input {
  width: 100%;
  padding: 14px 16px;
  border: 2px solid #ddd;
  border-radius: 12px;
  background: #fdfdfd;
  font-size: 15px;
  transition: all 0.2s;
  color: #1A1A1A;
}

.glass-input:focus {
  outline: none;
  border-color: #E31937;
  background: #fff;
  box-shadow: 0 0 0 4px rgba(227, 25, 55, 0.1);
}

.hint {
  color: #777;
  font-size: 13px;
}

.actions-group {
  display: flex;
  gap: 16px;
}

.submit-btn {
  background: #111;
  color: #fff;
  border: none;
  border-radius: 12px;
  padding: 14px 24px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.private-btn {
  background: transparent;
  color: #E31937;
  border: 2px solid #E31937;
}

.private-btn:hover:not(:disabled) {
  background: #E31937;
  color: #fff;
}

.submit-btn:hover:not(:disabled) {
  background: #000;
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0,0,0,0.15);
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spin {
  animation: spin 1s infinite linear;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.alert-box {
  margin-top: 24px;
  padding: 20px;
  border-radius: 12px;
  display: flex;
  gap: 16px;
}

.alert-box.error {
  background: #fff0f0;
  color: #d32f2f;
  border: 1px solid #ffcdd2;
  align-items: center;
}

.alert-box.success {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  align-items: flex-start;
}

.success-icon {
  color: #16a34a;
  flex-shrink: 0;
  margin-top: 2px;
}

.success-content h4 {
  margin: 0 0 8px 0;
  color: #166534;
  font-size: 18px;
}

.success-content p {
  color: #15803d;
  margin: 0 0 16px 0;
}

.badges {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.badge {
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
}

.badge.user {
  background: #dbeafe;
  color: #1e40af;
}

.badge.comp {
  background: #ffedd5;
  color: #c2410c;
}

.view-btn {
  display: inline-block;
  background: #16a34a;
  color: #fff;
  text-decoration: none;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 14px;
  transition: all 0.2s;
}

.view-btn:hover {
  background: #15803d;
  transform: translateY(-1px);
}

.fade-in {
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
