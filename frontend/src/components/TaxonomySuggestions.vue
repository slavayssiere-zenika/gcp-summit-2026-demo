<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import { Network, CheckCircle, XCircle, AlignLeft, Tag, Search, X } from 'lucide-vue-next'

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
  aliases: string | null
  sub_competencies?: CompetencyNode[]
}

// ── State ──────────────────────────────────────────────────────────────────
const suggestions = ref<Suggestion[]>([])
const loading = ref(true)
const error = ref('')
const processingId = ref<number | null>(null)

// Arbre des compétences (pour la modale alias)
const allCompetencies = ref<{ id: number; name: string; aliases: string | null }[]>([])
const loadingTree = ref(false)

// ── Modale "Ajouter comme alias" ──────────────────────────────────────────
const aliasModal = ref(false)
const aliasTarget = ref<Suggestion | null>(null)
const aliasSearch = ref('')
const aliasSelectedId = ref<number | null>(null)
const aliasProcessing = ref(false)

const filteredCompetencies = computed(() => {
  if (!aliasSearch.value.trim()) return allCompetencies.value.slice(0, 50)
  const q = aliasSearch.value.toLowerCase()
  return allCompetencies.value.filter(c =>
    c.name.toLowerCase().includes(q) || (c.aliases || '').toLowerCase().includes(q)
  ).slice(0, 50)
})

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

const fetchAllCompetencies = async () => {
  loadingTree.value = true
  try {
    // Récupère toutes les compétences à plat via la pagination
    const res = await axios.get('/api/competencies/?limit=2000')
    const items: CompetencyNode[] = res.data.items || []
    // Aplatissement récursif
    const flat: { id: number; name: string; aliases: string | null }[] = []
    const flatten = (nodes: CompetencyNode[]) => {
      for (const n of nodes) {
        flat.push({ id: n.id, name: n.name, aliases: n.aliases ?? null })
        if (n.sub_competencies?.length) flatten(n.sub_competencies)
      }
    }
    flatten(items)
    flat.sort((a, b) => a.name.localeCompare(b.name))
    allCompetencies.value = flat
  } catch (err) {
    console.error("Impossible de charger l'arbre.", err)
  } finally {
    loadingTree.value = false
  }
}

const reviewSuggestion = async (id: number, action: 'ACCEPT' | 'REJECT', payload: any = {}) => {
  processingId.value = id
  try {
    await axios.patch(`/api/competencies/suggestions/${id}/review`, { action, ...payload })
    suggestions.value = suggestions.value.filter(s => s.id !== id)
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message
    alert(`Erreur lors de la validation : ${msg}`)
  } finally {
    processingId.value = null
  }
}

// Accepter → créer à la racine (parent_id = null)
const onAccept = (suggestion: Suggestion) => {
  if (!confirm(`Ajouter "${suggestion.name}" comme nouvelle compétence racine ?\n\nElle sera placée à la racine de la taxonomie. Relancez le calcul de l'arbre ensuite.`)) return
  reviewSuggestion(suggestion.id, 'ACCEPT', {
    parent_id: null,
    description: `Importé depuis les suggestions missions (contexte: ${suggestion.context || 'inconnu'})`
  })
}

const onReject = (suggestion: Suggestion) => {
  if (confirm(`Rejeter la suggestion "${suggestion.name}" ? Elle ne sera plus proposée.`)) {
    reviewSuggestion(suggestion.id, 'REJECT')
  }
}

// Ouvrir la modale "Ajouter comme alias"
const openAliasModal = (suggestion: Suggestion) => {
  aliasTarget.value = suggestion
  aliasSearch.value = ''
  aliasSelectedId.value = null
  aliasModal.value = true
}

const closeAliasModal = () => {
  aliasModal.value = false
  aliasTarget.value = null
  aliasSelectedId.value = null
}

// Confirmer l'ajout d'alias
const confirmAlias = async () => {
  if (!aliasTarget.value || aliasSelectedId.value === null) return
  const comp = allCompetencies.value.find(c => c.id === aliasSelectedId.value)
  if (!comp) return

  aliasProcessing.value = true
  try {
    // Construire la nouvelle liste d'aliases en ajoutant le nom de la suggestion
    const existingAliases = (comp.aliases || '').split(',').map(a => a.trim()).filter(Boolean)
    const newAlias = aliasTarget.value.name.trim()
    if (!existingAliases.map(a => a.toLowerCase()).includes(newAlias.toLowerCase())) {
      existingAliases.push(newAlias)
    }
    const newAliasStr = existingAliases.join(', ')

    // PATCH la compétence cible avec les nouveaux aliases
    await axios.put(`/api/competencies/${comp.id}`, { aliases: newAliasStr })

    // REJECT la suggestion (elle est résolue via l'alias)
    await axios.patch(`/api/competencies/suggestions/${aliasTarget.value.id}/review`, {
      action: 'REJECT'
    })

    suggestions.value = suggestions.value.filter(s => s.id !== aliasTarget.value!.id)

    // Rafraîchir l'arbre local pour refléter le nouvel alias
    comp.aliases = newAliasStr

    closeAliasModal()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message
    alert(`Erreur lors de l'ajout de l'alias : ${msg}`)
  } finally {
    aliasProcessing.value = false
  }
}

onMounted(() => {
  fetchSuggestions()
  fetchAllCompetencies()
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
            <button
              class="btn alias"
              @click="openAliasModal(s)"
              :disabled="processingId === s.id || loadingTree"
              title="Associer à une compétence existante comme alias"
              :aria-label="`Ajouter ${s.name} comme alias d'une compétence existante`"
            >
              <Tag size="15" /> Ajouter comme alias
            </button>
            <button
              class="btn accept"
              @click="onAccept(s)"
              :disabled="processingId === s.id"
              title="Créer comme nouvelle compétence racine"
              :aria-label="`Accepter la compétence ${s.name} à la racine`"
            >
              <CheckCircle size="15" />
              <span v-if="processingId === s.id"><div class="btn-spinner"></div></span>
              <span v-else>Ajouter compétence</span>
            </button>
            <button
              class="btn reject"
              @click="onReject(s)"
              :disabled="processingId === s.id"
              title="Rejeter la suggestion"
              :aria-label="`Rejeter la suggestion ${s.name}`"
            >
              <XCircle size="15" /> Rejeter
            </button>
          </div>

        </div>
      </div>
    </div>
  </div>

  <!-- ── Modale : Ajouter comme alias ──────────────────────────────────── -->
  <Teleport to="body">
    <div v-if="aliasModal" class="modal-backdrop" @click.self="closeAliasModal" role="dialog" aria-modal="true" aria-labelledby="alias-modal-title">
      <div class="modal-box">
        <div class="modal-header">
          <div class="modal-title-group">
            <Tag size="18" class="modal-icon" />
            <h4 id="alias-modal-title">Ajouter comme alias de…</h4>
          </div>
          <button class="modal-close" @click="closeAliasModal" aria-label="Fermer la modale"><X size="18" /></button>
        </div>

        <div class="modal-body">
          <p class="modal-hint">
            La suggestion <strong>"{{ aliasTarget?.name }}"</strong> sera ajoutée aux aliases de la compétence sélectionnée, puis la suggestion sera rejetée.
          </p>

          <div class="search-box">
            <Search size="15" class="search-icon" />
            <input
              id="alias-search-input"
              v-model="aliasSearch"
              type="text"
              placeholder="Rechercher une compétence…"
              class="search-input"
              autocomplete="off"
            />
          </div>

          <div class="competency-list" role="listbox" aria-label="Liste des compétences">
            <div
              v-for="c in filteredCompetencies"
              :key="c.id"
              class="comp-item"
              :class="{ selected: aliasSelectedId === c.id }"
              @click="aliasSelectedId = c.id"
              role="option"
              :aria-selected="aliasSelectedId === c.id"
            >
              <span class="comp-name">{{ c.name }}</span>
              <span v-if="c.aliases" class="comp-aliases">{{ c.aliases }}</span>
            </div>
            <div v-if="filteredCompetencies.length === 0" class="no-results">Aucune compétence trouvée.</div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn reject" @click="closeAliasModal">Annuler</button>
          <button
            class="btn accept"
            :disabled="aliasSelectedId === null || aliasProcessing"
            @click="confirmAlias"
            aria-label="Confirmer l'ajout comme alias"
          >
            <div v-if="aliasProcessing" class="btn-spinner"></div>
            <Tag v-else size="15" />
            Confirmer l'alias
          </button>
        </div>
      </div>
    </div>
  </Teleport>
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

.panel-body { padding: 24px; }

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
  flex: 1;
  min-width: 0;
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
  max-width: 280px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.s-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── Buttons ── */
.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  font-size: 0.82rem;
  font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn.alias {
  background: #f5f3ff;
  color: #7c3aed;
  border-color: #ddd6fe;
}
.btn.alias:hover:not(:disabled) {
  background: #ede9fe;
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

.btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.7s infinite linear;
}

/* ── Modale ── */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 20px;
}

.modal-box {
  background: white;
  border-radius: 16px;
  width: 100%;
  max-width: 520px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  max-height: 80vh;
  overflow: hidden;
  animation: modal-in 0.2s ease;
}

@keyframes modal-in {
  from { opacity: 0; transform: translateY(-12px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 16px;
  border-bottom: 1px solid #f1f5f9;
}

.modal-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-icon { color: #7c3aed; }

h4 {
  font-size: 1rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  cursor: pointer;
  color: #94a3b8;
  border-radius: 6px;
  padding: 4px;
  transition: color 0.15s;
  display: flex;
}
.modal-close:hover { color: #1A1A1A; }

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
  flex: 1;
}

.modal-hint {
  font-size: 0.87rem;
  color: #475569;
  margin: 0;
  line-height: 1.5;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 12px;
  background: #f8fafc;
}

.search-icon { color: #94a3b8; flex-shrink: 0; }

.search-input {
  border: none;
  background: transparent;
  outline: none;
  font-size: 0.88rem;
  color: #0f172a;
  width: 100%;
}

.competency-list {
  overflow-y: auto;
  flex: 1;
  min-height: 120px;
  max-height: 260px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}

.comp-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid #f1f5f9;
  transition: background 0.12s;
}
.comp-item:last-child { border-bottom: none; }
.comp-item:hover { background: #f8fafc; }
.comp-item.selected {
  background: #f5f3ff;
  border-left: 3px solid #7c3aed;
}

.comp-name {
  font-weight: 600;
  font-size: 0.88rem;
  color: #0f172a;
}

.comp-aliases {
  font-size: 0.75rem;
  color: #94a3b8;
  font-style: italic;
}

.no-results {
  text-align: center;
  padding: 24px;
  color: #94a3b8;
  font-size: 0.87rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 24px;
  border-top: 1px solid #f1f5f9;
}
</style>
