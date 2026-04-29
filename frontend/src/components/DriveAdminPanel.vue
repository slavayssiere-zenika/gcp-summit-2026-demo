<template>
  <div class="drive-admin-panel">


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
            <div class="form-group">
              <input v-model="newFolder.excluded_folders_str" placeholder="Dossiers à exclure (ex: O1.old, _trash)" />
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
                <template v-if="editingFolderId === folder.id">
                  <td colspan="3">
                    <div class="edit-folder-form">
                      <div class="form-group" style="flex: 1;">
                        <label class="text-sm">Tag</label>
                        <input v-model="editFolderData.tag" class="w-full" style="padding: 0.4rem; border-radius: 4px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color);" />
                      </div>
                      <div class="form-group" style="flex: 2;">
                        <label class="text-sm">Exclusions (séparées par virgule)</label>
                        <input v-model="editFolderData.excluded_folders_str" class="w-full" style="padding: 0.4rem; border-radius: 4px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color);" />
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style="display: flex; flex-direction: column; gap: 0.4rem;">
                      <button @click="saveFolder(folder.id)" class="btn-action btn-sync" style="padding: 0.4rem 0.6rem; justify-content: center;" title="Sauvegarder" :disabled="isSaving">
                        <Loader2 v-if="isSaving" class="icon-sm spin" />
                        <template v-else>
                          <Check class="icon-sm" />
                          <span>Valider</span>
                        </template>
                      </button>
                      <button @click="cancelEdit" class="btn-action btn-retry" style="padding: 0.4rem 0.6rem; justify-content: center;" title="Annuler" :disabled="isSaving">
                        <X class="icon-sm" />
                        <span>Annuler</span>
                      </button>
                    </div>
                  </td>
                </template>
                <template v-else>
                  <td>
                    <div class="folder-info">
                      <span class="folder-name">{{ folder.folder_name || folder.google_folder_id }}</span>
                      <span class="tag-badge">{{ folder.tag }}</span>
                      <div v-if="folder.excluded_folders?.length" class="text-xs text-light" style="margin-top: 0.25rem;">
                        Exclus: {{ folder.excluded_folders.join(', ') }}
                      </div>
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
                    <div style="display: flex; gap: 0.5rem;">
                      <button v-if="isAdmin()" @click="startEditFolder(folder)" class="btn-icon btn-secondary" title="Éditer la source">
                        <Edit2 class="icon-sm" />
                      </button>
                      <button v-if="isAdmin()" @click="deleteFolder(folder.id)" class="btn-icon btn-danger" title="Supprimer la source">
                        <Trash2 class="icon-sm" />
                      </button>
                    </div>
                  </td>
                </template>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">
            <FolderX class="empty-icon" />
            <p>Aucun dossier source configuré.</p>
          </div>
        </div>
      </div>

      <!-- ── Dead Letter Queue Section ── -->
      <div class="errors-section dlq-section" v-if="dlqStatus && (dlqStatus.message_count > 0 || dlqStatus.error)">
        <div class="section-header-flex">
          <h3 class="danger-title">
            <AlertCircle class="icon-sm inline-icon" style="color: #f59e0b" />
            Dead Letter Queue (DLQ)
            <span class="dlq-badge" v-if="dlqStatus.message_count > 0">{{ dlqStatus.message_count }}</span>
            <span class="dlq-freshness" v-if="dlqLastFetchedAt">
              snapshot {{ dlqLastFetchedAt.toLocaleTimeString() }}
            </span>
          </h3>
          <div style="display:flex; gap:0.5rem; align-items:center">
            <button
              class="btn-icon-neutral"
              @click="fetchDlqStatus"
              :disabled="isFetchingDlq"
              title="Actualiser la liste DLQ"
              aria-label="Actualiser la Dead Letter Queue"
            >
              <RefreshCcw class="icon-sm" :class="{ 'spinning': isFetchingDlq }" />
            </button>
            <button
              v-if="dlqStatus.message_count > 0"
              class="btn-warning btn-sm"
              @click="replayDlq"
              :disabled="isReplayingDlq || !isAdmin()"
              :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Pull tous les messages DLQ, remet les CVs en PENDING et relance le pipeline'"
              aria-label="Rejouer les messages de la Dead Letter Queue"
            >
              <RefreshCcw class="icon-sm" :class="{ 'spinning': isReplayingDlq }" />
              {{ isReplayingDlq ? 'Replay en cours...' : `Rejouer DLQ (${dlqStatus.message_count})` }}
            </button>
          </div>
        </div>
        <div class="dlq-info">
          <p v-if="dlqStatus.error" class="dlq-error">⚠️ Erreur lecture DLQ : {{ dlqStatus.error }}</p>
          <template v-else-if="dlqStatus.message_count > 0">
            <p class="dlq-desc">
              <strong>{{ dlqStatus.message_count }}</strong> CV(s) ont échoué 5 fois sur le pipeline Pub/Sub et sont en attente dans
              <code>{{ dlqStatus.subscription }}</code>.
            </p>
            <!-- Liste des fichiers en DLQ -->
            <div class="dlq-file-list">
              <div
                v-for="file in dlqStatus.files"
                :key="file.google_file_id"
                class="dlq-file-row"
              >
                <FileText class="icon-sm dlq-file-icon" />
                <div class="dlq-file-info">
                  <span class="dlq-file-name">{{ file.file_name || file.google_file_id }}</span>
                  <span class="dlq-file-meta" v-if="file.parent_folder_name">
                    <User class="icon-xs" /> {{ file.parent_folder_name }}
                  </span>
                </div>
                <span class="dlq-file-status" :class="`status-${file.status?.toLowerCase()}`">
                  {{ file.status }}
                </span>
                <button
                  v-if="isAdmin()"
                  class="btn-icon-danger"
                  @click="deleteDlqMessage(file.google_file_id, '', file.ack_id)"
                  :title="`Supprimer de la DLQ (le CV sera ignoré définitivement)`"
                  aria-label="Supprimer ce message de la DLQ"
                >
                  <Trash2 class="icon-xs" />
                </button>
              </div>
              <div v-if="dlqStatus.unknown_files?.length" class="dlq-file-list">
                <div
                  v-for="unk in dlqStatus.unknown_files"
                  :key="unk.message_id"
                  class="dlq-file-row dlq-unknown-row"
                >
                  <div class="dlq-file-info dlq-unknown-info">
                    <div class="dlq-unknown-header">
                      <AlertCircle class="icon-sm" style="color:#f59e0b; flex-shrink:0" />
                      <span class="dlq-file-name" style="color:#f59e0b">Payload illisible</span>
                      <code class="dlq-msg-id">{{ unk.message_id }}</code>
                      <span v-if="unk.parse_error" class="dlq-parse-error">{{ unk.parse_error }}</span>
                    </div>
                    <pre class="dlq-json">{{ typeof unk.raw_data === 'string' ? unk.raw_data : JSON.stringify(unk.raw_data, null, 2) }}</pre>
                  </div>
                  <button
                    v-if="isAdmin()"
                    class="btn-icon-danger"
                    @click="deleteDlqMessage('', unk.message_id, unk.ack_id)"
                    title="Supprimer ce message de la DLQ"
                    aria-label="Supprimer ce payload illisible de la DLQ"
                  >
                    <Trash2 class="icon-xs" />
                  </button>
                </div>
              </div>
            </div>
          </template>
          <div v-if="dlqReplayResult" class="dlq-result">
            ✅ <strong>{{ dlqReplayResult.files_reset_to_pending }}</strong> CV(s) remis en PENDING ·
            {{ dlqReplayResult.dlq_messages_pulled }} messages purgés de la DLQ
            <span v-if="dlqReplayResult.unknown_payloads > 0" style="color:#f59e0b">
              · {{ dlqReplayResult.unknown_payloads }} payload(s) illisibles ignorés
            </span>
          </div>
        </div>
      </div>

      <!-- Action Requise / Errors List -->
      <div class="errors-section">
        <div class="section-header-flex">
          <h3 class="danger-title"><AlertCircle class="icon-sm inline-icon" /> Actions Requises (Erreurs)</h3>
          <div class="btn-group">
            <!-- Bouton Force Flush : visible quand des fichiers sont bloqués en QUEUED ou PROCESSING -->
            <button
              v-if="(syncStatus?.queued ?? 0) + (syncStatus?.processing ?? 0) > 0"
              class="btn-warning btn-sm"
              @click="forceFlushZombies"
              :disabled="isFlushingZombies || !isAdmin()"
              :title="!isAdmin() ? 'Réservé aux administrateurs' : `Reset immédiat des ${(syncStatus?.queued ?? 0) + (syncStatus?.processing ?? 0)} fichier(s) bloqués (QUEUED + PROCESSING) → PENDING`"
              aria-label="Forcer le déblocage des fichiers zombies bloqués en QUEUED ou PROCESSING"
            >
              <Zap class="icon-sm" :class="{ 'spinning': isFlushingZombies }" />
              {{ isFlushingZombies ? 'Déblocage...' : `Forcer Déblocage (${(syncStatus?.queued ?? 0) + (syncStatus?.processing ?? 0)})` }}
            </button>
            <button v-if="errorFiles.length > 0" class="btn-secondary btn-sm" @click="retryErrors" :disabled="isRetrying || !isAdmin()" :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Réessayer Tout'">
              <RefreshCcw class="icon-sm" :class="{ 'spinning': isRetrying }" />
              Réessayer Tout
            </button>
            <button v-if="errorFiles.length > 0" class="btn-danger btn-sm" @click="clearErrors" :disabled="isClearing || !isAdmin()" :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Purger toutes les erreurs'">
              <Trash2 class="icon-sm" />
              Purger Erreurs
            </button>
          </div>
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
      
      <!-- ── Graphe Drive Ingestion ── -->
      <DriveTreeGraph />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import axios from 'axios'
import DriveTreeGraph from './DriveTreeGraph.vue'
import {
  UploadCloud, Loader2, Clock, CheckCircle2, FileX, AlertCircle, Trash2, FolderX, Plus, RefreshCcw, User, Radio, Zap, FileText, Edit2, X, Check
} from 'lucide-vue-next'
import { authService } from '../services/auth'

const authHeader = () => ({ Authorization: `Bearer ${authService.state.token}` })
const isAdmin = () => authService.state.user?.role === 'admin'

const folders = ref<any[]>([])
const errorFiles = ref<any[]>([])
const syncStatus = ref<any>(null)
const isSyncing = ref(false)
const isAdding = ref(false)
const isRetrying = ref(false)
const isClearing = ref(false)
const isFlushingZombies = ref(false)
const newFolder = ref({ google_folder_id: '', tag: '', excluded_folders_str: '' })
const showAddFolder = ref(false)
const editingFolderId = ref<number | null>(null)
const editFolderData = ref({ tag: '', excluded_folders_str: '' })
const isSaving = ref(false)

const flushResult = ref<{zombies_reset: number, errors_reset: number} | null>(null)
const actionError = ref('')  // Message d'erreur visible dans l'UI

const startEditFolder = (folder: any) => {
  editingFolderId.value = folder.id
  editFolderData.value = {
    tag: folder.tag,
    excluded_folders_str: (folder.excluded_folders || []).join(', ')
  }
}

const cancelEdit = () => {
  editingFolderId.value = null
}

const saveFolder = async (folderId: number) => {
  if (isSaving.value) return
  isSaving.value = true
  try {
    const excluded = editFolderData.value.excluded_folders_str.split(',').map(s => s.trim()).filter(Boolean)
    await axios.patch(`/api/drive/folders/${folderId}`, {
      tag: editFolderData.value.tag,
      excluded_folders: excluded
    }, { headers: authHeader() })
    editingFolderId.value = null
    await fetchData()
  } catch (err: any) {
    actionError.value = "Erreur lors de la sauvegarde : " + (err.response?.data?.detail || err.message)
    setTimeout(() => actionError.value = '', 5000)
  } finally {
    isSaving.value = false
  }
}

// ── DLQ State ────────────────────────────────────────────────────────────────
interface DlqFile {
  google_file_id: string
  ack_id: string
  file_name: string | null
  parent_folder_name: string | null
  status: string
  last_processed_at: string | null
}
interface UnknownDlqFile {
  message_id: string
  ack_id: string
  raw_data: any
  parse_error: string | null
}
const dlqStatus = ref<{
  message_count: number
  subscription: string
  files: DlqFile[]
  unknown_files: UnknownDlqFile[]
  unknown_payloads?: number
  error?: string
} | null>(null)
const isReplayingDlq = ref(false)
const dlqReplayResult = ref<any>(null)

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
    const res = await axios.get('/api/drive/files?status=ERROR&limit=200')
    errorFiles.value = res.data.files || (Array.isArray(res.data) ? res.data : [])
  } catch (error) {
    console.error("Failed to load error files", error)
  }
}

const isFetchingDlq = ref(false)
const dlqLastFetchedAt = ref<Date | null>(null)

const fetchDlqStatus = async () => {
  if (isFetchingDlq.value) return  // eviter les appels concurrents
  isFetchingDlq.value = true
  try {
    const res = await axios.get('/api/drive/dlq/status', { headers: authHeader() })
    dlqStatus.value = res.data
    dlqLastFetchedAt.value = new Date()
  } catch (e) {
    console.debug('[DLQ] status fetch failed', e)
  } finally {
    isFetchingDlq.value = false
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
    await axios.post('/api/drive/retry-errors', {}, { headers: authHeader() })
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

const clearErrors = async () => {
  if (!confirm('Voulez-vous vraiment purger toutes les erreurs ? Les fichiers concernés seront marqués comme ignorés.')) return
  if (isClearing.value) return
  isClearing.value = true
  try {
    await axios.delete('/api/drive/errors', { headers: authHeader() })
    await fetchStatus()
    await fetchFolders()
    await fetchErrors()
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message || 'Erreur inconnue'
    actionError.value = `Purge des erreurs échouée : ${detail}`
    console.error('Failed to clear errors', err)
  } finally {
    isClearing.value = false
  }
}

const deleteDlqMessage = async (googleFileId: string, pubsubMessageId = '', ackId = '') => {
  const msg = googleFileId 
    ? 'Supprimer ce message de la DLQ ?\nLe fichier sera marqué comme IGNORÉ en base de données pour stopper les re-tentatives du système.' 
    : 'Supprimer ce payload illisible de la DLQ définitivement ?'
  if (!confirm(msg)) return
  try {
    const params = new URLSearchParams()
    if (ackId)           params.set('ack_id', ackId)
    if (googleFileId)    params.set('google_file_id', googleFileId)
    if (pubsubMessageId) params.set('pubsub_message_id', pubsubMessageId)
    await axios.delete(`/api/drive/dlq/message?${params}`, { headers: authHeader() })
    await fetchDlqStatus()
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message || 'Erreur inconnue'
    actionError.value = `Suppression DLQ échouée : ${detail}`
    console.error('DLQ delete failed', err)
  }
}

/**
 * Force le passage immédiat en PENDING de tous les fichiers QUEUED/PROCESSING
 * bloqués depuis plus de 0 secondes (bypass du seuil zombie de 30 min).
 * Utilisé quand des fichiers sont visiblement bloqués en file Pub/Sub.
 */
const forceFlushZombies = async () => {
  if (isFlushingZombies.value) return
  isFlushingZombies.value = true
  flushResult.value = null
  actionError.value = ''
  try {
    const res = await axios.post('/api/drive/retry-errors?force=true', {}, { headers: authHeader() })
    flushResult.value = res.data
    await fetchStatus()
    await fetchFolders()
    await fetchErrors()
    // Relancer le sync pour republier les PENDING dans Pub/Sub
    await triggerSync()
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.response?.data?.message || err.message || 'Erreur inconnue'
    actionError.value = `Déblocage échoué (HTTP ${err.response?.status ?? '?'}) : ${detail}`
    console.error('Force flush failed', err)
  } finally {
    isFlushingZombies.value = false
  }
}

/**
 * Rejoue les messages de la Dead Letter Queue :
 * Pull tous les messages DLQ → reset google_file_id en PENDING → ACK DLQ → /sync
 */
const replayDlq = async () => {
  if (isReplayingDlq.value) return
  isReplayingDlq.value = true
  dlqReplayResult.value = null
  actionError.value = ''
  try {
    const res = await axios.post('/api/drive/dlq/replay', {}, { headers: authHeader() })
    dlqReplayResult.value = res.data
    // Refresh DLQ count
    await fetchDlqStatus()
    await fetchStatus()
    // Republier les PENDING dans Pub/Sub
    if (res.data.files_reset_to_pending > 0) {
      await triggerSync()
    }
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message || 'Erreur inconnue'
    actionError.value = `Replay DLQ échoué (HTTP ${err.response?.status ?? '?'}) : ${detail}`
    console.error('DLQ replay failed', err)
  } finally {
    isReplayingDlq.value = false
  }
}

const addFolder = async () => {
  if (!newFolder.value.google_folder_id || !newFolder.value.tag) return
  isAdding.value = true
  try {
    const payload = {
      google_folder_id: newFolder.value.google_folder_id,
      tag: newFolder.value.tag,
      excluded_folders: newFolder.value.excluded_folders_str
        ? newFolder.value.excluded_folders_str.split(',').map(s => s.trim()).filter(s => s)
        : []
    }
    await axios.post('/api/drive/folders', payload, { headers: authHeader() })
    newFolder.value = { google_folder_id: '', tag: '', excluded_folders_str: '' }
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
    await axios.delete(`/api/drive/folders/${id}`, { headers: authHeader() })
    await fetchFolders()
  } catch (err) {
    console.error(err)
  }
}

const syncAuthError = ref('')

const triggerSync = async () => {
  isSyncing.value = true
  syncAuthError.value = ''
  actionError.value = ''
  try {
    await axios.post('/api/drive/sync')
    await fetchStatus()
    await fetchFolders()
  } catch (error: any) {
    const detail = error.response?.data?.detail || error.response?.data?.message || error.message || 'Erreur inconnue'
    if (error.response?.data?.message === 'SERVICE_ACCOUNT_ACCESS_LOSS') {
      syncAuthError.value = "Le Service Account a perdu ses droits sur le Google Drive (Permissions/OAuth annulées)."
    } else {
      actionError.value = `Sync échoué (HTTP ${error.response?.status ?? '?'}) : ${detail}`
    }
    console.error("Sync failed", error)
  } finally {
    isSyncing.value = false
  }
}

onMounted(() => {
  fetchFolders()
  fetchStatus()
  fetchErrors()
  fetchDlqStatus()  // chargement unique au mount
  pollInterval = setInterval(() => {
    fetchStatus()
    fetchFolders()
    if (syncStatus.value?.errors > 0 || errorFiles.value.length > 0) {
      fetchErrors()
    }
    // DLQ : refresh silencieux toutes les 60s pour renouveler les ack_ids (expire à 600s)
    // NE PAS mettre dans le polling 5s — cela provoque des oscillations du compteur Pub/Sub
    const now = Date.now()
    const lastFetch = dlqLastFetchedAt.value?.getTime() ?? 0
    if (now - lastFetch > 60_000) {
      fetchDlqStatus()
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

/* ── DLQ Styles ── */
.dlq-section {
  border-left: 3px solid #f59e0b;
  background: rgba(245, 158, 11, 0.04);
}

.dlq-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #f59e0b;
  color: #000;
  font-size: 0.7rem;
  font-weight: 700;
  border-radius: 999px;
  padding: 0.1rem 0.5rem;
  min-width: 1.5rem;
}

.dlq-info {
  padding: 0.5rem 0;
  font-size: 0.85rem;
  color: var(--text-secondary, #aaa);
}

.dlq-desc {
  line-height: 1.6;
  margin: 0.25rem 0;
}

.dlq-desc code {
  background: rgba(255,255,255,0.08);
  border-radius: 4px;
  padding: 0.1rem 0.4rem;
  font-size: 0.8rem;
}

.dlq-result {
  margin-top: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: rgba(34, 197, 94, 0.08);
  border-radius: 6px;
  border-left: 3px solid #22c55e;
  font-size: 0.85rem;
  color: #22c55e;
}

.dlq-error {
  color: #f59e0b;
}

.dlq-file-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-top: 0.5rem;
}

.dlq-file-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.4rem 0.6rem;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 6px;
  font-size: 0.83rem;
}

.dlq-file-icon {
  flex-shrink: 0;
  color: #f59e0b;
  opacity: 0.8;
}

.dlq-file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  overflow: hidden;
}

.dlq-file-name {
  color: var(--text-primary, #e5e7eb);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dlq-file-meta {
  color: var(--text-secondary, #6b7280);
  font-size: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.icon-xs {
  width: 10px;
  height: 10px;
}

.dlq-file-status {
  flex-shrink: 0;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  background: rgba(255,255,255,0.08);
  color: #9ca3af;
}

.status-processing { background: rgba(251, 146, 60, 0.15); color: #fb923c; }
.status-error      { background: rgba(239, 68, 68, 0.15);  color: #ef4444; }
.status-pending    { background: rgba(156, 163, 175, 0.15); color: #9ca3af; }
.status-queued     { background: rgba(99, 102, 241, 0.15);  color: #818cf8; }
.status-imported_cv{ background: rgba(34, 197, 94, 0.15);  color: #22c55e; }

.dlq-unknown {
  color: #f59e0b;
  font-style: italic;
  gap: 0.5rem;
}

.dlq-unknown-row {
  flex-direction: row;
  align-items: flex-start;
  padding: 0.5rem 0.6rem;
}

.dlq-unknown-info {
  flex-direction: column;
  gap: 0.4rem;
}

.dlq-unknown-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.dlq-msg-id {
  font-size: 0.7rem;
  background: rgba(255,255,255,0.06);
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  color: #6b7280;
  font-family: monospace;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dlq-parse-error {
  font-size: 0.72rem;
  color: #ef4444;
  font-style: italic;
}

.dlq-json {
  margin: 0;
  padding: 0.5rem 0.6rem;
  background: rgba(0, 0, 0, 0.25);
  border-radius: 5px;
  font-family: monospace;
  font-size: 0.72rem;
  color: #d1d5db;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 150px;
  overflow-y: auto;
  border-left: 2px solid #f59e0b;
}


.btn-icon-danger {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: #6b7280;
  transition: color 0.15s, background 0.15s;
  padding: 0;
}

.btn-icon-danger:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.btn-icon-neutral {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  cursor: pointer;
  color: #9ca3af;
  transition: color 0.15s, background 0.15s;
  padding: 0;
}

.btn-icon-neutral:hover:not(:disabled) {
  color: #e5e7eb;
  background: rgba(255, 255, 255, 0.12);
}

.btn-icon-neutral:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dlq-freshness {
  font-size: 0.68rem;
  font-weight: 400;
  color: #6b7280;
  margin-left: 0.4rem;
  font-style: italic;
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

.edit-folder-form {
  display: flex;
  gap: 1rem;
  align-items: flex-end;
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

.btn-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Bouton d'urgence pour le force flush — orange pour signaler l'aspect critique */
.btn-warning {
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
  border: 1px solid rgba(245, 158, 11, 0.35);
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s ease;
  animation: pulseWarning 2.5s ease-in-out infinite;
}
.btn-warning:hover:not(:disabled) {
  background: rgba(245, 158, 11, 0.22);
  border-color: rgba(245, 158, 11, 0.6);
}
.btn-warning:disabled { opacity: 0.6; cursor: not-allowed; animation: none; }

@keyframes pulseWarning {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
  50% { box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.18); }
}
</style>
