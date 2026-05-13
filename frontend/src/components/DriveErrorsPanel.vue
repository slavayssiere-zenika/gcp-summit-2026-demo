<template>
  <div class="errors-panel">

    <!-- ── Bannière d'alerte proéminente ── -->
    <div v-if="errorFiles.length > 0" class="alert-banner">
      <div class="alert-icon-wrap">
        <XCircle size="28" />
      </div>
      <div class="alert-body">
        <div class="alert-title">
          {{ errorFiles.length }} CV{{ errorFiles.length > 1 ? 's' : '' }} en erreur d'ingestion
        </div>
        <div class="alert-subtitle">
          Ces fichiers ont échoué lors du pipeline Drive → CV.
          Pour les ré-analyser en masse, utilisez le <strong>Pipeline Vertex AI Batch</strong>.
          Vous pouvez aussi re-tenter l'import individuellement via le bouton « Importer ».
        </div>
      </div>
      <div class="alert-actions">
        <button
          class="btn-retry-all"
          @click="goToBulkImport"
          :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Lancer une ré-analyse via Vertex AI Batch'"
          :disabled="!isAdmin()"
        >
          <Zap size="14" />
          Ré-analyse Batch
        </button>
        <button
          class="btn-purge"
          @click="purgeAll"
          :disabled="isClearing || !isAdmin()"
          :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Marquer tous comme ignorés'"
        >
          <Trash2 size="14" />
          {{ isClearing ? 'Purge…' : 'Purger' }}
        </button>
      </div>
    </div>

    <!-- ── Succès : aucune erreur ── -->
    <div v-else-if="!isLoading" class="no-errors-state">
      <CheckCircle2 size="40" />
      <p>Aucune erreur d'ingestion détectée.</p>
      <span class="no-errors-sub">Tous les CVs ont été traités avec succès.</span>
    </div>

    <!-- ── Loading initial ── -->
    <div v-if="isLoading && errorFiles.length === 0" class="loading-state">
      <Loader2 size="28" class="spinning" />
      <p>Chargement des erreurs…</p>
    </div>

    <!-- ── Feedback action ── -->
    <div v-if="actionFeedback" class="action-feedback" :class="actionFeedback.type">
      <template v-if="actionFeedback.type === 'success'">✅ {{ actionFeedback.message }}</template>
      <template v-else>❌ {{ actionFeedback.message }}</template>
    </div>

    <!-- ── Filtres & Pagination controls ── -->
    <div v-if="errorFiles.length > 0" class="toolbar-row">
      <div class="filter-group">
        <label class="filter-label">
          <FolderOpen size="13" />
          Agence
        </label>
        <select v-model="selectedFolderId" class="filter-select">
          <option :value="null">Toutes les agences</option>
          <option v-for="folder in uniqueFolders" :key="folder.id" :value="folder.id">
            {{ folder.name }} ({{ folder.count }})
          </option>
        </select>
      </div>
      <div class="pagination-info">
        <span>{{ filteredFiles.length }} CV{{ filteredFiles.length > 1 ? 's' : '' }}</span>
        <span v-if="totalPages > 1"> · Page {{ currentPage }}/{{ totalPages }}</span>
      </div>
    </div>

    <!-- ── Liste des erreurs ── -->
    <div v-if="paginatedFiles.length > 0" class="error-list">
      <div
        v-for="file in paginatedFiles"
        :key="file.google_file_id"
        class="error-card"
        :class="{ 'importing': importingIds.has(file.google_file_id) }"
      >
        <div class="error-card-header">
          <div class="file-meta">
            <FileText size="15" class="file-icon" />
            <div class="file-info">
              <span class="file-name">{{ file.file_name || file.google_file_id }}</span>
              <span class="file-path">
                <FolderOpen size="11" />
                {{ file.parent_folder_name || 'Racine' }}
              </span>
            </div>
          </div>
          <div class="card-right">
            <span class="folder-tag" v-if="getFolderTag(file.folder_id)">
              {{ getFolderTag(file.folder_id) }}
            </span>
            <span class="retry-count" v-if="file.retry_count > 0" title="Nombre de tentatives">
              <RotateCcw size="11" />
              {{ file.retry_count }}/3
            </span>
            <button
              class="btn-import"
              @click="importSingle(file)"
              :disabled="importingIds.has(file.google_file_id) || !isAdmin()"
              :title="!isAdmin() ? 'Réservé aux administrateurs' : 'Remettre en file d\'attente'"
            >
              <Loader2 v-if="importingIds.has(file.google_file_id)" size="13" class="spinning" />
              <Upload v-else size="13" />
              {{ importingIds.has(file.google_file_id) ? 'Envoi…' : 'Importer' }}
            </button>
          </div>
        </div>

        <!-- Message d'erreur (accordion) -->
        <div class="error-toggle" @click="toggleExpand(file.google_file_id)">
          <ChevronDown size="13" :class="{ rotated: expandedIds.has(file.google_file_id) }" />
          <span>{{ expandedIds.has(file.google_file_id) ? 'Masquer' : 'Voir' }} le message d'erreur</span>
        </div>
        <div v-if="expandedIds.has(file.google_file_id)" class="error-log">
          <pre>{{ file.error_message || 'Erreur inconnue. Aucun détail fourni par le backend.' }}</pre>
        </div>
      </div>
    </div>

    <!-- ── Pagination ── -->
    <div v-if="totalPages > 1" class="pagination">
      <button class="page-btn" @click="currentPage--" :disabled="currentPage === 1">
        <ChevronLeft size="14" />
      </button>
      <span class="page-indicator">{{ currentPage }} / {{ totalPages }}</span>
      <button class="page-btn" @click="currentPage++" :disabled="currentPage === totalPages">
        <ChevronRight size="14" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import axios from 'axios'
import { useRouter } from 'vue-router'
import {
  XCircle, CheckCircle2, Trash2, Loader2, FileText,
  FolderOpen, Upload, ChevronDown, ChevronLeft, ChevronRight,
  RotateCcw, Zap
} from 'lucide-vue-next'
import { authService } from '../services/auth'

// ── Props / Emits ──────────────────────────────────────────────────────────────
interface Props {
  folders?: Array<{ id: number; tag: string; folder_name: string | null }>
}
const props = withDefaults(defineProps<Props>(), { folders: () => [] })

const emit = defineEmits<{
  (e: 'errorCountChanged', count: number): void
}>()

const router = useRouter()

// ── Auth ───────────────────────────────────────────────────────────────────────
const authHeader = () => ({ Authorization: `Bearer ${authService.state.token}` })
const isAdmin = () => authService.state.user?.role === 'admin'

// ── State ──────────────────────────────────────────────────────────────────────
interface ErrorFile {
  google_file_id: string
  file_name: string | null
  parent_folder_name: string | null
  folder_id: number
  error_message: string | null
  retry_count: number
  last_processed_at: string | null
}

const errorFiles = ref<ErrorFile[]>([])
const isLoading = ref(false)
const isClearing = ref(false)
const importingIds = ref<Set<string>>(new Set())
const expandedIds = ref<Set<string>>(new Set())
const selectedFolderId = ref<number | null>(null)
const currentPage = ref(1)
const PAGE_SIZE = 20
const actionFeedback = ref<{ type: 'success' | 'error'; message: string } | null>(null)

let pollInterval: ReturnType<typeof setInterval> | null = null

// ── Computed ───────────────────────────────────────────────────────────────────
const getFolderTag = (folderId: number): string => {
  const f = props.folders.find(x => x.id === folderId)
  return f ? f.tag : ''
}

const uniqueFolders = computed(() => {
  const map = new Map<number, { id: number; name: string; count: number }>()
  for (const f of errorFiles.value) {
    if (!map.has(f.folder_id)) {
      const folder = props.folders.find(x => x.id === f.folder_id)
      map.set(f.folder_id, {
        id: f.folder_id,
        name: folder?.folder_name || folder?.tag || `Dossier #${f.folder_id}`,
        count: 0,
      })
    }
    map.get(f.folder_id)!.count++
  }
  return Array.from(map.values()).sort((a, b) => b.count - a.count)
})

const filteredFiles = computed(() => {
  if (selectedFolderId.value === null) return errorFiles.value
  return errorFiles.value.filter(f => f.folder_id === selectedFolderId.value)
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredFiles.value.length / PAGE_SIZE)))

const paginatedFiles = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return filteredFiles.value.slice(start, start + PAGE_SIZE)
})

// Reset page quand le filtre change
watch(selectedFolderId, () => { currentPage.value = 1 })

// ── Data Fetching ──────────────────────────────────────────────────────────────
const fetchErrors = async () => {
  isLoading.value = true
  try {
    const res = await axios.get('/api/drive/files?status=ERROR&limit=500', { headers: authHeader() })
    errorFiles.value = res.data.files || (Array.isArray(res.data) ? res.data : [])
    emit('errorCountChanged', errorFiles.value.length)
  } catch (err) {
    console.error('[DriveErrorsPanel] fetchErrors failed', err)
  } finally {
    isLoading.value = false
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────────
const showFeedback = (type: 'success' | 'error', message: string) => {
  actionFeedback.value = { type, message }
  setTimeout(() => { actionFeedback.value = null }, 4000)
}

const toggleExpand = (id: string) => {
  const next = new Set(expandedIds.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  expandedIds.value = next
}

// ── Actions ────────────────────────────────────────────────────────────────────
const importSingle = async (file: ErrorFile) => {
  const next = new Set(importingIds.value)
  next.add(file.google_file_id)
  importingIds.value = next
  try {
    await axios.patch(
      `/api/drive/files/${file.google_file_id}`,
      { status: 'PENDING', error_message: null },
      { headers: authHeader() }
    )
    await axios.post('/api/drive/sync', {}, { headers: authHeader() })
    showFeedback('success', `"${file.file_name || file.google_file_id}" remis en file d'attente.`)
    await fetchErrors()
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message || 'Erreur inconnue'
    showFeedback('error', `Import échoué : ${detail}`)
    console.error('[DriveErrorsPanel] importSingle failed', err)
  } finally {
    const next2 = new Set(importingIds.value)
    next2.delete(file.google_file_id)
    importingIds.value = next2
  }
}

// Ré-analyse bulk : redirige vers AdminBulkImport qui utilise Vertex AI Batch
// (le retry-errors direct est interdit en masse car il by-passe Vertex)
const goToBulkImport = () => {
  router.push('/admin/bulk-import')
}

const purgeAll = async () => {
  if (!confirm('Voulez-vous vraiment purger toutes les erreurs ? Les fichiers seront marqués comme ignorés.')) return
  if (isClearing.value) return
  isClearing.value = true
  try {
    const res = await axios.delete('/api/drive/errors', { headers: authHeader() })
    showFeedback('success', `${res.data.cleared_count ?? 0} erreur(s) purgée(s).`)
    await fetchErrors()
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message || 'Erreur inconnue'
    showFeedback('error', `Purge échouée : ${detail}`)
    console.error('[DriveErrorsPanel] purgeAll failed', err)
  } finally {
    isClearing.value = false
  }
}

// ── Lifecycle ──────────────────────────────────────────────────────────────────
onMounted(() => {
  fetchErrors()
  // Polling toutes les 20s pour mettre à jour le compteur
  pollInterval = setInterval(fetchErrors, 20_000)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})

// Expose pour permettre au parent de forcer un refresh
defineExpose({ fetchErrors })
</script>

<style scoped>
.errors-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* ── Bannière alerte ── */
.alert-banner {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.25rem 1.5rem;
  background: linear-gradient(135deg, rgba(220, 38, 38, 0.12) 0%, rgba(239, 68, 68, 0.08) 100%);
  border: 1.5px solid rgba(220, 38, 38, 0.35);
  border-left: 4px solid #dc2626;
  border-radius: 14px;
  animation: pulseAlert 3s ease-in-out infinite;
}
@keyframes pulseAlert {
  0%, 100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
  50% { box-shadow: 0 0 0 6px rgba(220, 38, 38, 0.08); }
}

.alert-icon-wrap {
  flex-shrink: 0;
  color: #dc2626;
  display: flex;
  align-items: center;
}

.alert-body {
  flex: 1;
  min-width: 0;
}

.alert-title {
  font-size: 1rem;
  font-weight: 800;
  color: #dc2626;
  margin-bottom: 3px;
}

.alert-subtitle {
  font-size: 0.78rem;
  color: #991b1b;
  opacity: 0.85;
  line-height: 1.4;
}

.alert-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.btn-retry-all {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: rgba(139, 92, 246, 0.12);
  color: #7c3aed;
  border: 1px solid rgba(139, 92, 246, 0.35);
  border-radius: 10px;
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.btn-retry-all:hover:not(:disabled) { background: rgba(139, 92, 246, 0.22); }
.btn-retry-all:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-purge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
  border: 1px solid rgba(220, 38, 38, 0.3);
  border-radius: 10px;
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.btn-purge:hover:not(:disabled) { background: rgba(220, 38, 38, 0.18); }
.btn-purge:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── No errors ── */
.no-errors-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 3rem 2rem;
  color: #16a34a;
  background: rgba(22, 163, 74, 0.06);
  border: 1px solid rgba(22, 163, 74, 0.2);
  border-radius: 16px;
  text-align: center;
}
.no-errors-state p {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: #16a34a;
}
.no-errors-sub {
  font-size: 0.8rem;
  color: #15803d;
  opacity: 0.75;
}

/* ── Loading ── */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 2.5rem;
  color: #94a3b8;
}
.loading-state p { margin: 0; font-size: 0.85rem; }

/* ── Feedback ── */
.action-feedback {
  padding: 10px 16px;
  border-radius: 10px;
  font-size: 0.83rem;
  font-weight: 600;
}
.action-feedback.success {
  background: rgba(22, 163, 74, 0.08);
  color: #166534;
  border: 1px solid rgba(22, 163, 74, 0.25);
}
.action-feedback.error {
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
  border: 1px solid rgba(220, 38, 38, 0.25);
}

/* ── Toolbar ── */
.toolbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.78rem;
  font-weight: 600;
  color: #64748b;
  white-space: nowrap;
}

.filter-select {
  padding: 6px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.8);
  color: #1e293b;
  font-size: 0.8rem;
  cursor: pointer;
  outline: none;
  transition: border-color 0.2s;
}
.filter-select:focus { border-color: #94a3b8; }

.pagination-info {
  font-size: 0.78rem;
  color: #64748b;
  font-weight: 600;
}

/* ── Error List ── */
.error-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.error-card {
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(220, 38, 38, 0.18);
  border-left: 3px solid rgba(220, 38, 38, 0.5);
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.error-card:hover {
  border-color: rgba(220, 38, 38, 0.35);
  box-shadow: 0 2px 12px rgba(220, 38, 38, 0.08);
}
.error-card.importing {
  opacity: 0.65;
  pointer-events: none;
}

.error-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.file-icon {
  flex-shrink: 0;
  color: #dc2626;
  opacity: 0.7;
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.file-name {
  font-size: 0.85rem;
  font-weight: 700;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 380px;
}

.file-path {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.72rem;
  color: #64748b;
}

.card-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.folder-tag {
  font-size: 0.68rem;
  background: rgba(99, 102, 241, 0.1);
  color: #4f46e5;
  border: 1px solid rgba(99, 102, 241, 0.25);
  padding: 2px 8px;
  border-radius: 20px;
  font-weight: 700;
  white-space: nowrap;
}

.retry-count {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 0.7rem;
  color: #d97706;
  font-weight: 600;
  background: rgba(217, 119, 6, 0.08);
  border: 1px solid rgba(217, 119, 6, 0.2);
  padding: 2px 7px;
  border-radius: 20px;
  white-space: nowrap;
}

.btn-import {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  background: rgba(22, 163, 74, 0.1);
  color: #166534;
  border: 1px solid rgba(22, 163, 74, 0.3);
  border-radius: 8px;
  font-size: 0.78rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.btn-import:hover:not(:disabled) {
  background: rgba(22, 163, 74, 0.2);
  border-color: rgba(22, 163, 74, 0.5);
}
.btn-import:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Accordion ── */
.error-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  font-size: 0.73rem;
  color: #94a3b8;
  cursor: pointer;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  background: rgba(0, 0, 0, 0.015);
  transition: background 0.15s, color 0.15s;
  user-select: none;
}
.error-toggle:hover { background: rgba(0, 0, 0, 0.04); color: #64748b; }
.error-toggle svg { transition: transform 0.2s; flex-shrink: 0; }
.error-toggle svg.rotated { transform: rotate(180deg); }

.error-log {
  padding: 10px 14px;
  background: rgba(254, 242, 242, 0.6);
  border-top: 1px solid rgba(220, 38, 38, 0.08);
}
.error-log pre {
  margin: 0;
  font-size: 0.78rem;
  color: #991b1b;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Menlo', 'Monaco', monospace;
  line-height: 1.5;
}

/* ── Pagination ── */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  color: #475569;
  transition: all 0.15s;
}
.page-btn:hover:not(:disabled) { background: #f1f5f9; border-color: #cbd5e1; }
.page-btn:disabled { opacity: 0.35; cursor: not-allowed; }

.page-indicator {
  font-size: 0.8rem;
  font-weight: 700;
  color: #475569;
  min-width: 60px;
  text-align: center;
}

/* ── Animation ── */
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
