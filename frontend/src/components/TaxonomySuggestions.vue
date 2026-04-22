<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { Network, CheckCircle, XCircle, ChevronDown, AlignLeft } from 'lucide-vue-next'

// ── Types ──────────────────────────────────────────────────────────────────
interface Suggestion {
  id: number
  name: string
  source: string
  context: string | null
  occurrence_count: number
  status: string
  created_at: string
}

interface CompetencyNode {
  id: number
  name: string
  sub_competencies?: CompetencyNode[]
}

// ── State ──────────────────────────────────────────────────────────────────
const suggestions = ref<Suggestion[]>([])
const loading = ref(true)
const error = ref('')

const treeNodes = ref<CompetencyNode[]>([])
const loadingTree = ref(false)

const processingId = ref<number | null>(null)

// ── Flatten Tree for select ──────────────────────────────────────────────
const flatTree = ref<{ id: number, label: string }[]>([])

const flattenNode = (node: CompetencyNode, depth = 0) => {
  const prefix = '—'.repeat(depth)
  flatTree.value.push({ id: node.id, label: `${prefix} ${node.name}` })
  if (node.sub_competencies) {
    node.sub_competencies.forEach(sub => flattenNode(sub, depth + 1))
  }
}

// ── Actions ────────────────────────────────────────────────────────────────
const fetchSuggestions = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/competencies/suggestions?status=PENDING_REVIEW')
    suggestions.value = res.data || []
  } catch (err: any) {
    error.value = "Impossible de charger les suggestions."
    console.error(err)
  } finally {
    loading.value = false
  }
}

const fetchTree = async () => {
  loadingTree.value = true
  try {
    const res = await axios.get('/api/competencies/?limit=1000')
    treeNodes.value = res.data.items || []
    
    flatTree.value = []
    treeNodes.value.forEach(node => flattenNode(node, 0))
  } catch (err) {
    console.error("Impossible de charger l'arbre pour les suggestions.", err)
  } finally {
    loadingTree.value = false
  }
}

const reviewSuggestion = async (id: number, action: 'ACCEPT' | 'REJECT', payload: any = {}) => {
  processingId.value = id
  try {
    await axios.patch(`/api/competencies/suggestions/${id}/review`, {
      action,
      ...payload
    })
    // Retirer de la liste
    suggestions.value = suggestions.value.filter(s => s.id !== id)
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message
    alert(`Erreur lors de la validation: ${msg}`)
  } finally {
    processingId.value = null
  }
}

const onAccept = (suggestion: Suggestion) => {
  // Petite modale native pour simplifier, on pourrait faire une modale custom
  const parentIdStr = window.prompt(
    `Accepter la compétence "${suggestion.name}"\n\nVeuillez entrer l'ID du Noeud Parent (laissez vide pour noeud racine) :\n\n` + 
    flatTree.value.slice(0, 30).map(t => `${t.id} - ${t.label}`).join('\n') + (flatTree.value.length > 30 ? '\n...' : '')
  )
  
  if (parentIdStr === null) return // Cancelled

  let parentId: number | undefined
  if (parentIdStr.trim() !== '') {
    parentId = parseInt(parentIdStr.trim())
    if (isNaN(parentId)) {
      alert("L'ID parent doit être un nombre valide.")
      return
    }
  }

  const descStr = window.prompt(`Description pour "${suggestion.name}" (facultatif):`, `Autogénéré depuis la mission: ${suggestion.context || 'inconnu'}`)
  
  if (descStr === null) return // Cancelled

  reviewSuggestion(suggestion.id, 'ACCEPT', {
    parent_id: parentId,
    description: descStr || undefined
  })
}

const onReject = (suggestion: Suggestion) => {
  if (confirm(`Voulez-vous rejeter la suggestion "${suggestion.name}" ?\nElle ne sera plus proposée.`)) {
    reviewSuggestion(suggestion.id, 'REJECT')
  }
}

onMounted(() => {
  fetchSuggestions()
  fetchTree()
})
</script>

<template>
  <div class="glass-panel">
    <div class="card-header">
      <div class="title-group">
        <Network class="icon-title" size="20" />
        <h3>Suggestions de Taxonomie (Missions)</h3>
      </div>
      <div class="badge" v-if="suggestions.length > 0">{{ suggestions.length }}</div>
    </div>

    <div class="panel-body">
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
      </div>
      <div v-else-if="error" class="error-msg">{{ error }}</div>
      <div v-else-if="suggestions.length === 0" class="empty-state">
        Toutes les suggestions ont été traitées.
      </div>
      <div v-else class="suggestions-list">
        <div v-for="s in suggestions" :key="s.id" class="suggestion-item">
          
          <div class="s-info">
            <span class="s-name">{{ s.name }}</span>
            <div class="s-meta">
              <span class="s-count" title="Nombre d'occurrences extraites">{{ s.occurrence_count }} occ.</span>
              <span class="s-context"><AlignLeft size="12" /> {{ s.context || 'Aucun contexte' }}</span>
              <span class="s-date">{{ new Date(s.created_at).toLocaleDateString() }}</span>
            </div>
          </div>

          <div class="s-actions">
            <button class="btn accept" @click="onAccept(s)" :disabled="processingId === s.id" title="Accepter et ajouter à la taxonomie">
              <CheckCircle size="16" /> Accepter
            </button>
            <button class="btn reject" @click="onReject(s)" :disabled="processingId === s.id" title="Rejeter la suggestion">
              <XCircle size="16" /> Rejeter
            </button>
          </div>

        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.glass-panel {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  margin-bottom: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  background: #fafafa;
}

.title-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.icon-title { color: #E31937; }

h3 {
  font-size: 1.1rem;
  font-weight: 700;
  color: #1A1A1A;
  margin: 0;
}

.badge {
  background: #E31937;
  color: white;
  font-size: 0.75rem;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 20px;
}

.panel-body {
  padding: 24px;
}

.loading-state, .empty-state, .error-msg {
  text-align: center;
  padding: 40px 20px;
  color: #64748b;
  font-size: 0.95rem;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid rgba(227, 25, 55, 0.2);
  border-top-color: #E31937;
  border-radius: 50%;
  animation: spin 1s infinite linear;
  margin: 0 auto;
}

@keyframes spin { to { transform: rotate(360deg); } }

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.suggestion-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  transition: all 0.2s;
  flex-wrap: wrap;
  gap: 16px;
}

.suggestion-item:hover {
  border-color: #cbd5e1;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
}

.s-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.s-name {
  font-weight: 700;
  font-size: 1.05rem;
  color: #0f172a;
}

.s-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.8rem;
  color: #64748b;
  flex-wrap: wrap;
}

.s-count {
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
  color: #334155;
}

.s-context {
  display: flex;
  align-items: center;
  gap: 4px;
  max-width: 300px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.s-actions {
  display: flex;
  gap: 8px;
}

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  font-size: 0.85rem;
  font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn.accept {
  background: #f0fdf4;
  color: #16a34a;
  border-color: #bbf7d0;
}
.btn.accept:hover:not(:disabled) {
  background: #dcfce7;
}

.btn.reject {
  background: #fef2f2;
  color: #dc2626;
  border-color: #fecaca;
}
.btn.reject:hover:not(:disabled) {
  background: #fee2e2;
}
</style>
