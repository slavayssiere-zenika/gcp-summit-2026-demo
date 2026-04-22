<template>
  <div class="drive-admin-panel">
    <div class="admin-header">
      <div class="header-content">
        <h2>Google Drive Scanner</h2>
        <p class="subtitle">Import automatisé et taggé des CV depuis Google Drive</p>
      </div>
      <div class="action-container">
        <button class="btn-primary" @click="triggerSync" :disabled="isSyncing">
          <UploadCloud v-if="!isSyncing" class="icon" />
          <Loader2 v-else class="icon spinning" />
          {{ isSyncing ? 'Synchronisation...' : 'Forcer Synchronisation' }}
        </button>
      </div>
    </div>

    <!-- Alert for OAuth loss -->
    <div class="error-panel fade-in-up auth-alert" v-if="syncAuthError">
      <strong>🚨 Alerte Critique :</strong> {{ syncAuthError }}
    </div>
    
    <!-- Sync loader global -->
    <div class="global-sync-alert" v-if="isProcessingOrPending">
      <Radio v-if="syncStatus?.queued > 0" class="icon" />
      <Loader2 v-else class="icon spinning" />
      <span>{{ queuedBannerMsg || 'Analyse et import en cours en arrière-plan...' }}</span>
    </div>

    <!-- Dashboard Widget -->
    <div class="stats-grid" v-if="syncStatus">
      <div class="stat-card">
        <div class="stat-icon pending"><Clock class="icon" /></div>
        <div class="stat-content">
          <span class="label">En Attente (PENDING)</span>
          <span class="value">{{ syncStatus.pending }}</span>
        </div>
      </div>
      <div class="stat-card" :class="{ 'queued-card-active': syncStatus.queued > 0 }">
        <div class="stat-icon queued"><Radio class="icon" /></div>
        <div class="stat-content">
          <span class="label">File Pub/Sub (QUEUED)</span>
          <span class="value">{{ syncStatus.queued || 0 }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon processing"><Loader2 class="icon spinning" /></div>
        <div class="stat-content">
          <span class="label">En cours (PROCESSING)</span>
          <span class="value">{{ syncStatus.processing }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon imported"><CheckCircle2 class="icon" /></div>
        <div class="stat-content">
          <span class="label">CV Importés</span>
          <span class="value">{{ syncStatus.imported }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon ignored"><FileX class="icon" /></div>
        <div class="stat-content">
          <span class="label">Ignorés (Non CV)</span>
          <span class="value">{{ syncStatus.ignored }}</span>
        </div>
      </div>
      <div class="stat-card error-card-stat">
        <div class="stat-icon error"><AlertCircle class="icon" /></div>
        <div class="stat-content">
          <span class="label">Erreurs d'import</span>
          <span class="value">{{ syncStatus.errors }}</span>
        </div>
      </div>
    </div>

    <div class="main-split">
      <!-- Main Content: Folders -->
      <div class="folders-section">
        <div class="section-header-flex">
          <h3>Dossiers Cibles</h3>
          <button class="btn-secondary btn-sm" @click="showAddFolder = !showAddFolder">
            <Plus class="icon-sm" /> Ajouter
          </button>
        </div>
        
        <div v-if="showAddFolder" class="card add-folder-card">
          <h4>Ajouter une source Drive</h4>
          <form @submit.prevent="addFolder" class="inline-form">
            <div class="form-group">
              <input v-model="newFolder.google_folder_id" placeholder="ID du dossier (Google Drive)" required />
            </div>
            <div class="form-group">
              <input v-model="newFolder.tag" placeholder="Tag (ex: Paris, Lille)" required />
            </div>
            <button type="submit" class="btn-primary" :disabled="isAdding">
              <Plus class="icon-sm" /> Inscrire la source
            </button>
          </form>
        </div>

        <div class="card table-card">
          <table v-if="folders.length > 0" class="data-table">
            <thead>
              <tr>
                <th>Dossier / Tag</th>
                <th style="min-width: 200px;">Progression</th>
                <th>Statut</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="folder in folders" :key="folder.id">
                <td>
                  <div class="folder-info">
                    <span class="folder-name">{{ folder.folder_name || folder.google_folder_id }}</span>
                    <span class="tag-badge">{{ folder.tag }}</span>
                  </div>
                </td>
                <td>
                  <div v-if="folder.stats && folder.stats.total_files > 0" class="progress-wrapper">
                    <div class="progress-bar">
                      <div class="progress-fill imported" :style="{ width: percent(folder.stats.imported, folder.stats.total_files) }"></div>
                      <div class="progress-fill ignored" :style="{ width: percent(folder.stats.ignored, folder.stats.total_files) }"></div>
                      <div class="progress-fill error" :style="{ width: percent(folder.stats.errors, folder.stats.total_files) }"></div>
                    </div>
                    <div class="progress-text text-sm">
                      {{ folder.stats.imported + folder.stats.errors + folder.stats.ignored }} / {{ folder.stats.total_files }} traités
                    </div>
                  </div>
                  <div v-else class="text-sm text-light">En attente de scan...</div>
                </td>
                <td>
                  <div v-if="folder.stats">
                    <span v-if="folder.stats.processing > 0" class="status-badge processing">En cours ({{ folder.stats.processing }})</span>
                    <span v-else-if="folder.stats.errors > 0" class="status-badge error">{{ folder.stats.errors }} Erreurs</span>
                    <span v-else-if="folder.stats.pending > 0" class="status-badge pending">En attente</span>
                    <span v-else-if="folder.stats.total_files > 0" class="status-badge imported_cv">Terminé</span>
                  </div>
                </td>
                <td>
                  <button @click="deleteFolder(folder.id)" class="btn-icon btn-danger" title="Supprimer la source">
                    <Trash2 class="icon-sm" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">
            <FolderX class="empty-icon" />
            <p>Aucun dossier source configuré.</p>
          </div>
        </div>
      </div>

      <!-- Action Requise / Errors List -->
      <div class="errors-section">
        <div class="section-header-flex">
          <h3 class="danger-title"><AlertCircle class="icon-sm inline-icon" /> Actions Requises (Erreurs)</h3>
          <button v-if="errorFiles.length > 0" class="btn-secondary btn-sm" @click="retryErrors" :disabled="isRetrying">
            <RefreshCcw class="icon-sm" :class="{ 'spinning': isRetrying }" />
            Réessayer Tout
          </button>
        </div>

        <div v-if="errorFiles.length > 0" class="error-list">
          <div v-for="file in errorFiles" :key="file.google_file_id" class="error-card">
            <div class="error-card-header">
              <div class="file-identity">
                <strong>{{ file.file_name || file.google_file_id }}</strong>
                <span class="file-path">{{ file.parent_folder_name || 'Racine' }}</span>
              </div>
              <span class="tag-badge">{{ getFolderTag(file.folder_id) }}</span>
            </div>
            <div class="error-log">
              <pre>{{ file.error_message || 'Erreur inconnue. Aucun détail fourni par le backend.' }}</pre>
            </div>
          </div>
        </div>
        <div v-else class="card empty-state success-state">
          <CheckCircle2 class="empty-icon success-icon" />
          <p>Aucune erreur en attente.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import axios from 'axios'
import {
  UploadCloud, Loader2, Clock, CheckCircle2, FileX, AlertCircle, Trash2, FolderX, Plus, RefreshCcw, User, Radio
} from 'lucide-vue-next'

const folders = ref<any[]>([])
const errorFiles = ref<any[]>([])
const syncStatus = ref<any>(null)
const isSyncing = ref(false)
const isAdding = ref(false)
const isRetrying = ref(false)
const newFolder = ref({ google_folder_id: '', tag: '' })
const showAddFolder = ref(false)

const isProcessingOrPending = computed(() => {
  if (!syncStatus.value) return false;
  return syncStatus.value.processing > 0 || syncStatus.value.pending > 0 || syncStatus.value.queued > 0;
})

const queuedBannerMsg = computed(() => {
  if (!syncStatus.value) return '';
  const q = syncStatus.value.queued || 0;
  const p = syncStatus.value.processing || 0;
  if (q > 0 && p > 0) return `${q} CV(s) en file Pub/Sub · ${p} en traitement actif par l'IA...`;
  if (q > 0) return `${q} CV(s) en file Pub/Sub — traitement IA en attente de démarrage...`;
  if (p > 0) return `${p} CV(s) en cours d'analyse par l'IA (Gemini)...`;
  return '';
})

let pollInterval: any = null

const fetchFolders = async () => {
  try {
    const res = await axios.get('/api/drive/folders')
    folders.value = res.data
  } catch (error) {
    console.error("Failed to load folders", error)
  }
}

const fetchStatus = async () => {
  try {
    const res = await axios.get('/api/drive/status')
    syncStatus.value = res.data
  } catch (error) {
    console.error("Failed to load status", error)
  }
}

const fetchErrors = async () => {
  try {
    // Only fetch files with ERROR status, using the new parameter
    const res = await axios.get('/api/drive/files?status=ERROR&limit=200')
    errorFiles.value = res.data
  } catch (error) {
    console.error("Failed to load error files", error)
  }
}

const getFolderTag = (folderId: number) => {
  const f = folders.value.find(x => x.id === folderId)
  return f ? f.tag : 'Inconnu'
}

const percent = (value: number, total: number) => {
  if (!total) return '0%';
  return `${Math.round((value / total) * 100)}%`;
}

const retryErrors = async () => {
  if (isRetrying.value) return
  isRetrying.value = true
  try {
    await axios.post('/api/drive/retry-errors')
    await fetchStatus()
    await fetchFolders()
    await fetchErrors()
    triggerSync() 
  } catch (err) {
    console.error('Failed to retry errors', err)
  } finally {
    isRetrying.value = false
  }
}

const addFolder = async () => {
  if (!newFolder.value.google_folder_id || !newFolder.value.tag) return
  isAdding.value = true
  try {
    await axios.post('/api/drive/folders', newFolder.value)
    newFolder.value = { google_folder_id: '', tag: '' }
    showAddFolder.value = false
    await fetchFolders()
    triggerSync()
  } catch (err) {
    alert("Erreur lors de l'ajout.")
  } finally {
    isAdding.value = false
  }
}

const deleteFolder = async (id: number) => {
  if (!confirm('Voulez-vous retirer cette source ? La file d\'attente existante ne sera pas détruite.')) return
  try {
    await axios.delete(`/api/drive/folders/${id}`)
    await fetchFolders()
  } catch (err) {
    console.error(err)
  }
}

const syncAuthError = ref('')

const triggerSync = async () => {
  isSyncing.value = true
  syncAuthError.value = ''
  try {
    await axios.post('/api/drive/sync')
    await fetchStatus()
    await fetchFolders()
  } catch (error: any) {
    console.error("Sync failed", error)
    if (error.response?.data?.message === 'SERVICE_ACCOUNT_ACCESS_LOSS') {
      syncAuthError.value = "Le Service Account a perdu ses droits sur le Google Drive (Permissions/OAuth annulées)."
    }
  } finally {
    isSyncing.value = false
  }
}

onMounted(() => {
  fetchFolders()
  fetchStatus()
  fetchErrors()
  pollInterval = setInterval(() => {
    fetchStatus()
    fetchFolders()
    if (syncStatus.value?.errors > 0 || errorFiles.value.length > 0) {
      fetchErrors()
    }
  }, 5000)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})
</script>

<style scoped>
.drive-admin-panel {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.admin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.action-container {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.global-sync-alert {
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid rgba(59, 130, 246, 0.3);
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-weight: 500;
  animation: fadeIn 0.3s ease;
}

.auth-alert {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-5px); }
  to { opacity: 1; transform: translateY(0); }
}

.subtitle {
  color: var(--text-light);
  margin-top: 0.25rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
}

.stat-card {
  background: var(--surface-light);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  transition: all 0.2s ease;
}

.error-card-stat {
  background: rgba(239, 68, 68, 0.05);
  border-color: rgba(239, 68, 68, 0.2);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.stat-icon.pending { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
.stat-icon.queued { background: rgba(139, 92, 246, 0.1); color: #8b5cf6; }
.stat-icon.processing { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
.stat-icon.imported { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.stat-icon.ignored { background: rgba(107, 114, 128, 0.1); color: #6b7280; }
.stat-icon.error { background: rgba(239, 68, 68, 0.1); color: #ef4444; }

.queued-card-active {
  border-color: rgba(139, 92, 246, 0.4);
  background: rgba(139, 92, 246, 0.05);
  animation: pulseQueued 2s ease-in-out infinite;
}

@keyframes pulseQueued {
  0%, 100% { box-shadow: 0 0 0 0 rgba(139, 92, 246, 0); }
  50% { box-shadow: 0 0 0 6px rgba(139, 92, 246, 0.15); }
}


.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-content .label {
  font-size: 0.875rem;
  color: var(--text-light);
  font-weight: 500;
}

.stat-content .value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-color);
}

.main-split {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
}
@media (min-width: 1024px) {
  .main-split {
    grid-template-columns: 1fr 1fr;
  }
}

.card {
  background: var(--surface-light);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 1.5rem;
}

.section-header-flex {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.section-header-flex h3 {
  margin: 0;
}

.danger-title {
  color: #ef4444;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.add-folder-card {
  margin-bottom: 1rem;
  background: var(--bg-color);
}

.inline-form {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  margin-top: 1rem;
}

.form-group input {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color);
  min-width: 200px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th, .data-table td {
  padding: 1rem;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.data-table th {
  font-weight: 600;
  color: var(--text-light);
  font-size: 0.875rem;
}

.folder-info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.3rem;
}

.folder-name {
  font-weight: 600;
  color: var(--text-color);
}

.tag-badge {
  background: var(--primary-color);
  color: white;
  padding: 0.15rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 500;
}

.progress-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--bg-color);
  border-radius: 999px;
  overflow: hidden;
  display: flex;
}

.progress-fill {
  height: 100%;
}
.progress-fill.imported { background: #10b981; }
.progress-fill.ignored { background: #6b7280; }
.progress-fill.error { background: #ef4444; }

.status-badge {
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.status-badge.pending { background: rgba(245, 158, 11, 0.15); color: #d97706; }
.status-badge.processing { background: rgba(59, 130, 246, 0.15); color: #2563eb; }
.status-badge.imported_cv { background: rgba(16, 185, 129, 0.15); color: #059669; }
.status-badge.error { background: rgba(239, 68, 68, 0.15); color: #dc2626; }

.error-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.error-card {
  background: rgba(239, 68, 68, 0.03);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 8px;
  overflow: hidden;
}

.error-card-header {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid rgba(239, 68, 68, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.file-identity {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.file-path {
  font-size: 0.75rem;
  color: var(--text-light);
}

.error-log {
  padding: 1rem;
  background: var(--bg-color);
}
.error-log pre {
  margin: 0;
  font-size: 0.85rem;
  color: #dc2626;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.success-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  color: #10b981;
  background: rgba(16, 185, 129, 0.05);
  border-color: rgba(16, 185, 129, 0.2);
}
.success-icon {
  color: #10b981;
  opacity: 1;
}

.empty-state {
  text-align: center;
  padding: 3rem 0;
  color: var(--text-light);
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.btn-secondary {
  background: var(--surface-color);
  color: var(--text-color);
  border: 1px solid var(--border-color);
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: 500;
}
.btn-secondary:hover { background: var(--bg-color); }
.btn-primary {
  background: var(--primary-color);
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s ease;
}
.btn-primary:hover:not(:disabled) {
  background: #c3132e;
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 6px;
  display: inline-flex;
  transition: all 0.2s ease;
}
.btn-danger { color: #ef4444; }
.btn-danger:hover { background: rgba(239, 68, 68, 0.1); }
.btn-sm { padding: 0.5rem 1rem; font-size: 0.875rem; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }
.text-sm { font-size: 0.875rem; }
.text-light { color: var(--text-light); }
</style>
