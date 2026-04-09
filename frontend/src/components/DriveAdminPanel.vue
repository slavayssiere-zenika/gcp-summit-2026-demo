<template>
  <div class="drive-admin-panel">
    <div class="admin-header">
      <div class="header-content">
        <h2>Google Drive Scanner</h2>
        <p class="subtitle">Import automatisé et taggé des CV depuis Google Drive</p>
      </div>
      <div class="action-container">
        <span v-if="syncStartedMsg" class="sync-msg">{{ syncStartedMsg }}</span>
        <button class="btn-primary" @click="triggerSync" :disabled="isSyncing">
          <UploadCloud v-if="!isSyncing" class="icon" />
          <Loader2 v-else class="icon spinning" />
          {{ isSyncing ? 'Synchronisation...' : 'Forcer Synchronisation' }}
        </button>
      </div>
    </div>

    <!-- Dashboard Widget -->
    <div class="stats-grid" v-if="syncStatus">
      <div class="stat-card">
        <div class="stat-icon pending"><Clock class="icon" /></div>
        <div class="stat-content">
          <span class="label">En Attente (Queue)</span>
          <span class="value">{{ syncStatus.pending }}</span>
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
      <div class="stat-card">
        <div class="stat-icon error"><AlertCircle class="icon" /></div>
        <div class="stat-content">
          <span class="label">Erreurs d'import</span>
          <span class="value">{{ syncStatus.errors }}</span>
        </div>
        <button v-if="syncStatus.errors && syncStatus.errors > 0" class="btn-retry" @click="retryErrors" title="Réessayer tous les fichiers en erreur">
          <RefreshCcw class="icon-sm" :class="{ 'spinning': isRetrying }" />
        </button>
      </div>
    </div>

    <!-- Configuration Table -->
    <div class="folders-section">
      <h3>Dossiers Sources Inscrits</h3>
      <div class="card table-card">
        <table v-if="folders.length > 0" class="data-table">
          <thead>
            <tr>
              <th>Google Folder ID</th>
              <th>Tag Associé</th>
              <th>Date d'ajout</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="folder in folders" :key="folder.id">
              <td class="font-mono text-sm">{{ folder.google_folder_id }}</td>
              <td><span class="tag-badge">{{ folder.tag }}</span></td>
              <td>{{ formatDate(folder.created_at) }}</td>
              <td>
                <button @click="deleteFolder(folder.id)" class="btn-icon btn-danger" title="Supprimer">
                  <Trash2 class="icon-sm" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        
        <div v-else class="empty-state">
          <FolderX class="empty-icon" />
          <p>Aucun dossier source configuré. Le scanner est inactif.</p>
        </div>

        <div class="add-folder-form">
          <h4>Ajouter une source Drive</h4>
          <form @submit.prevent="addFolder" class="inline-form">
            <div class="form-group">
              <input v-model="newFolder.google_folder_id" placeholder="ID du dossier (Google Drive)" required />
            </div>
            <div class="form-group">
              <input v-model="newFolder.tag" placeholder="Tag (ex: Paris, Lille)" required />
            </div>
            <button type="submit" class="btn-secondary" :disabled="isAdding">
              <Plus class="icon-sm" /> Ajouter
            </button>
          </form>
        </div>
      </div>
    </div>

    <!-- Files Table -->
    <div class="files-section">
      <h3>Fichiers Historisés</h3>
      <div class="card table-card">
        <table v-if="files.length > 0" class="data-table">
          <thead>
            <tr>
              <th>Nom du Fichier</th>
              <th>Tag</th>
              <th>Statut</th>
              <th>Dernière exécution</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="file in files" :key="file.google_file_id">
              <td class="font-medium">{{ file.file_name || file.google_file_id }}</td>
              <td><span class="tag-badge">{{ getFolderTag(file.folder_id) }}</span></td>
              <td>
                <span class="status-badge" :class="file.status.toLowerCase()">
                  {{ formatStatus(file.status) }}
                </span>
              </td>
              <td class="text-sm">{{ formatDate(file.last_processed_at || file.modified_time) }}</td>
            </tr>
          </tbody>
        </table>
        
        <div v-else class="empty-state">
          <p>Aucun fichier encore analysé.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import {
  UploadCloud, Loader2, Clock, CheckCircle2, FileX, AlertCircle, Trash2, FolderX, Plus, RefreshCcw
} from 'lucide-vue-next'

const folders = ref<any[]>([])
const files = ref<any[]>([])
const syncStatus = ref<any>(null)
const isSyncing = ref(false)
const isAdding = ref(false)
const isRetrying = ref(false)
const newFolder = ref({ google_folder_id: '', tag: '' })

let pollInterval: any = null

const fetchFolders = async () => {
  try {
    const res = await axios.get('/drive-api/folders')
    folders.value = res.data
  } catch (error) {
    console.error("Failed to load folders", error)
  }
}

const fetchStatus = async () => {
  try {
    const res = await axios.get('/drive-api/status')
    syncStatus.value = res.data
  } catch (error) {
    console.error("Failed to load status", error)
  }
}

const fetchFiles = async () => {
  try {
    const res = await axios.get('/drive-api/files')
    files.value = res.data
  } catch (error) {
    console.error("Failed to load files", error)
  }
}

const getFolderTag = (folderId: number) => {
  const f = folders.value.find(x => x.id === folderId)
  return f ? f.tag : 'Inconnu'
}

const formatStatus = (status: string) => {
  const map: Record<string, string> = {
    'PENDING': 'En Attente',
    'IMPORTED_CV': 'Importé',
    'IGNORED_NOT_CV': 'Ignoré',
    'ERROR': 'Erreur'
  }
  return map[status] || status
}

const retryErrors = async () => {
  if (isRetrying.value) return
  isRetrying.value = true
  try {
    await axios.post('/drive-api/retry-errors')
    await fetchStatus()
    await fetchFiles()
    triggerSync() // trigger sync to process pending items immediately
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
    await axios.post('/drive-api/folders', newFolder.value)
    newFolder.value = { google_folder_id: '', tag: '' }
    await fetchFolders()
    // Manually trigger a background sync to wake up the worker
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
    await axios.delete(`/drive-api/folders/${id}`)
    await fetchFolders()
  } catch (err) {
    console.error(err)
  }
}

const syncStartedMsg = ref('')

const triggerSync = async () => {
  isSyncing.value = true
  try {
    await axios.post('/drive-api/sync')
    syncStartedMsg.value = 'Synchronisation démarrée en arrière-plan...'
    setTimeout(() => { syncStartedMsg.value = '' }, 3000)
    await fetchStatus()
  } catch (error) {
    console.error("Sync failed", error)
  } finally {
    isSyncing.value = false
  }
}

const formatDate = (ds: string) => {
  if (!ds) return 'N/A'
  return new Date(ds).toLocaleString('fr-FR', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}

onMounted(() => {
  fetchFolders()
  fetchStatus()
  fetchFiles()
  pollInterval = setInterval(() => {
    fetchStatus()
    fetchFiles()
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

.sync-msg {
  color: #10b981;
  font-weight: 500;
  font-size: 0.9rem;
  animation: fadeIn 0.3s ease;
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

.stat-card:hover {
  border-color: var(--primary-light);
  transform: translateY(-2px);
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
.stat-icon.imported { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.stat-icon.ignored { background: rgba(107, 114, 128, 0.1); color: #6b7280; }
.stat-icon.error { background: rgba(239, 68, 68, 0.1); color: #ef4444; }

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

.card {
  background: var(--surface-light);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 1.5rem;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 2rem;
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

.tag-badge {
  background: var(--primary-color);
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 500;
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
  min-width: 250px;
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

.btn-secondary:hover {
  background: var(--bg-color);
}

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
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.2);
  transition: all 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background: #c3132e;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(227, 25, 55, 0.3);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

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

.spinning { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

.font-mono { font-family: monospace; }
.text-sm { font-size: 0.875rem; }

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

.status-badge {
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.status-badge.pending { background: rgba(245, 158, 11, 0.15); color: #d97706; }
.status-badge.imported_cv { background: rgba(16, 185, 129, 0.15); color: #059669; }
.status-badge.ignored_not_cv { background: rgba(107, 114, 128, 0.15); color: #4b5563; }
.status-badge.error { background: rgba(239, 68, 68, 0.15); color: #dc2626; border: 1px solid rgba(239, 68, 68, 0.3); }

.btn-retry {
  background: var(--surface-light);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #ef4444;
  padding: 0.5rem;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-left: auto;
}

.btn-retry:hover {
  background: rgba(239, 68, 68, 0.1);
}

.font-medium {
  font-weight: 500;
  color: var(--text-color);
}
</style>
