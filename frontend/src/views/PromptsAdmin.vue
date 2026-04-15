<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'
import {
  BrainCircuit, Search, Wand2, Save, RefreshCw, ChevronRight,
  Clock, Hash, AlertTriangle, CheckCircle2, Loader2, X,
  ArrowLeftRight, FileText, BarChart3, Circle
} from 'lucide-vue-next'
import { useUxStore } from '@/stores/uxStore'

const uxStore = useUxStore()

// ─── State ────────────────────────────────────────────────────────────────────

interface Prompt {
  key: string
  value: string
  updated_at?: string
  agent?: string
}

const prompts = ref<Prompt[]>([])
const originalPrompts = ref<Record<string, string>>({})
const loading = ref(true)
const savingKey = ref<string | null>(null)
const analyzingKey = ref<string | null>(null)
const selectedKey = ref<string | null>(null)
const searchQuery = ref('')

// Analysis modal
const showModal = ref(false)
const analysisResult = ref<{ key: string; data: any } | null>(null)
const activeModalTab = ref<'analysis' | 'suggestion' | 'diff'>('suggestion')

// ─── Computed ─────────────────────────────────────────────────────────────────

const selectedPrompt = computed(() =>
  prompts.value.find(p => p.key === selectedKey.value) ?? null
)

const filteredPrompts = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  if (!q) return prompts.value
  return prompts.value.filter(p => p.key.toLowerCase().includes(q))
})

const isDirty = (key: string) => {
  const p = prompts.value.find(p => p.key === key)
  return p ? originalPrompts.value[key] !== p.value : false
}

const dirtyCount = computed(() => prompts.value.filter(p => isDirty(p.key)).length)

// Token estimator: ~4 chars per token (GPT-style heuristic)
const estimatedTokens = computed(() => {
  const val = selectedPrompt.value?.value ?? ''
  return Math.ceil(val.length / 4)
})

const charCount = computed(() => selectedPrompt.value?.value?.length ?? 0)

// Diff computation for modal
const diffLines = computed(() => {
  if (!analysisResult.value) return []
  const original = originalPrompts.value[analysisResult.value.key] ?? ''
  const improved = analysisResult.value.data.improved_prompt ?? ''
  const oldLines = original.split('\n')
  const newLines = improved.split('\n')
  const maxLen = Math.max(oldLines.length, newLines.length)
  return Array.from({ length: maxLen }, (_, i) => ({
    old: oldLines[i] ?? null,
    new: newLines[i] ?? null,
    changed: oldLines[i] !== newLines[i]
  }))
})

// ─── Methods ──────────────────────────────────────────────────────────────────

const fetchPrompts = async () => {
  try {
    loading.value = true
    const res = await axios.get('/api/prompts/')
    prompts.value = res.data
    res.data.forEach((p: Prompt) => {
      originalPrompts.value[p.key] = p.value
    })
    if (res.data.length > 0 && !selectedKey.value) {
      selectedKey.value = res.data[0].key
    }
  } catch (e: any) {
    uxStore.showToast('Erreur lors du chargement des prompts : ' + e.message, 'error')
  } finally {
    loading.value = false
  }
}

const selectPrompt = (key: string) => {
  selectedKey.value = key
}

const updatePrompt = async (prompt: Prompt) => {
  try {
    savingKey.value = prompt.key
    const res = await axios.put(`/api/prompts/${prompt.key}`, { value: prompt.value })
    originalPrompts.value[prompt.key] = res.data.value
    uxStore.showToast(`✅ "${prompt.key}" sauvegardé avec succès`, 'success')
  } catch (e: any) {
    uxStore.showToast('Erreur lors de la sauvegarde : ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    savingKey.value = null
  }
}

const analyzePrompt = async (prompt: Prompt) => {
  try {
    analyzingKey.value = prompt.key
    const res = await axios.post(`/api/prompts/${prompt.key}/analyze`)
    analysisResult.value = { key: prompt.key, data: res.data }
    activeModalTab.value = 'suggestion'
    showModal.value = true
  } catch (e: any) {
    uxStore.showToast("Erreur d'analyse : " + (e.response?.data?.detail || e.message), 'error')
  } finally {
    analyzingKey.value = null
  }
}

const acceptImprovedPrompt = async () => {
  if (!analysisResult.value) return
  const target = prompts.value.find(p => p.key === analysisResult.value!.key)
  if (target) {
    target.value = analysisResult.value.data.improved_prompt
    await updatePrompt(target)
  }
  closeModal()
}

const closeModal = () => {
  showModal.value = false
  analysisResult.value = null
}

const formatDate = (iso?: string) => {
  if (!iso) return 'Jamais modifié'
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}

// Close modal on Escape
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && showModal.value) closeModal()
}

onMounted(() => {
  fetchPrompts()
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="pa-root">

    <!-- ── Page Header ─────────────────────────────────────────────────────── -->
    <header class="pa-header">
      <div class="pa-header-left">
        <div class="pa-header-icon">
          <BrainCircuit size="22" />
        </div>
        <div>
          <h1 class="pa-title">Administration des AI Prompts</h1>
          <p class="pa-subtitle">Gestion dynamique des directives système Gemini</p>
        </div>
      </div>
      <div class="pa-header-right">
        <span v-if="dirtyCount > 0" class="pa-dirty-badge">
          <Circle size="8" class="pulse-dot" />
          {{ dirtyCount }} modification{{ dirtyCount > 1 ? 's' : '' }} non sauvegardée{{ dirtyCount > 1 ? 's' : '' }}
        </span>
        <button class="pa-btn-icon" @click="fetchPrompts" title="Rafraîchir" aria-label="Rafraîchir les prompts">
          <RefreshCw size="16" />
        </button>
      </div>
    </header>

    <!-- ── Loading State ──────────────────────────────────────────────────── -->
    <div v-if="loading" class="pa-loading">
      <div class="pa-skeleton-sidebar">
        <div v-for="i in 4" :key="i" class="skeleton-item"></div>
      </div>
      <div class="pa-skeleton-editor">
        <div class="skeleton-row header-row"></div>
        <div class="skeleton-row"></div>
        <div class="skeleton-row short"></div>
        <div class="skeleton-row"></div>
        <div class="skeleton-row short"></div>
      </div>
    </div>

    <!-- ── Empty State ────────────────────────────────────────────────────── -->
    <div v-else-if="prompts.length === 0" class="pa-empty">
      <FileText size="48" class="pa-empty-icon" />
      <h3>Aucun prompt configuré</h3>
      <p>Exécutez le seeder backend pour initialiser les instructions.</p>
    </div>

    <!-- ── Split View ─────────────────────────────────────────────────────── -->
    <div v-else class="pa-split">

      <!-- Sidebar -->
      <aside class="pa-sidebar">
        <div class="pa-search-wrapper">
          <Search size="15" class="pa-search-icon" />
          <input
            v-model="searchQuery"
            type="text"
            class="pa-search-input"
            placeholder="Rechercher un prompt…"
            aria-label="Rechercher un prompt"
          />
        </div>

        <div class="pa-sidebar-count">
          {{ filteredPrompts.length }} prompt{{ filteredPrompts.length > 1 ? 's' : '' }}
        </div>

        <nav class="pa-nav" aria-label="Liste des prompts">
          <button
            v-for="p in filteredPrompts"
            :key="p.key"
            class="pa-nav-item"
            :class="{ active: selectedKey === p.key, dirty: isDirty(p.key) }"
            @click="selectPrompt(p.key)"
            :aria-current="selectedKey === p.key ? 'true' : 'false'"
          >
            <div class="pa-nav-item-inner">
              <span class="pa-nav-key">{{ p.key }}</span>
              <ChevronRight size="14" class="pa-nav-chevron" />
            </div>
            <div class="pa-nav-meta">
              <span class="pa-nav-chars">{{ p.value?.length ?? 0 }} car.</span>
              <span v-if="isDirty(p.key)" class="pa-dirty-dot" aria-label="Modifications non sauvegardées"></span>
            </div>
          </button>

          <div v-if="filteredPrompts.length === 0" class="pa-no-results">
            Aucun résultat pour « {{ searchQuery }} »
          </div>
        </nav>
      </aside>

      <!-- Editor Panel -->
      <main class="pa-editor-panel" v-if="selectedPrompt">
        <!-- Editor Header -->
        <div class="pa-editor-header">
          <div class="pa-editor-title-row">
            <h2 class="pa-editor-key">{{ selectedPrompt.key }}</h2>
            <span v-if="isDirty(selectedPrompt.key)" class="pa-unsaved-badge">
              <AlertTriangle size="12" /> Non sauvegardé
            </span>
          </div>
          <div class="pa-editor-meta">
            <span class="pa-meta-chip">
              <Clock size="12" /> {{ formatDate(selectedPrompt.updated_at) }}
            </span>
            <span class="pa-meta-chip">
              <Hash size="12" /> {{ charCount }} caractères
            </span>
            <span class="pa-meta-chip" :class="{ 'chip-warning': estimatedTokens > 8000 }">
              <BrainCircuit size="12" /> ~{{ estimatedTokens.toLocaleString() }} tokens
            </span>
          </div>
        </div>

        <!-- Textarea -->
        <div class="pa-textarea-wrapper">
          <textarea
            v-model="selectedPrompt.value"
            class="pa-textarea"
            placeholder="Instructions système pour le modèle IA..."
            aria-label="Contenu du prompt"
            spellcheck="false"
          ></textarea>
          <div class="pa-textarea-footer">
            <span class="pa-line-count">
              {{ selectedPrompt.value?.split('\n').length ?? 0 }} lignes
            </span>
            <div class="pa-char-bar">
              <div
                class="pa-char-fill"
                :style="{ width: Math.min((charCount / 32000) * 100, 100) + '%' }"
                :class="{ danger: charCount > 28000 }"
              ></div>
            </div>
            <span class="pa-char-limit">/ ~32k max</span>
          </div>
        </div>

        <!-- Actions -->
        <div class="pa-actions">
          <button
            class="pa-btn-analyze"
            @click="analyzePrompt(selectedPrompt)"
            :disabled="!!analyzingKey"
            aria-label="Analyser et améliorer le prompt avec l'IA"
          >
            <Loader2 v-if="analyzingKey === selectedPrompt.key" size="16" class="spin" />
            <Wand2 v-else size="16" />
            {{ analyzingKey === selectedPrompt.key ? 'Analyse IA en cours…' : 'Analyser & Améliorer' }}
          </button>

          <button
            class="pa-btn-save"
            @click="updatePrompt(selectedPrompt)"
            :disabled="!isDirty(selectedPrompt.key) || savingKey === selectedPrompt.key"
            aria-label="Sauvegarder les modifications"
          >
            <Loader2 v-if="savingKey === selectedPrompt.key" size="16" class="spin" />
            <Save v-else size="16" />
            {{ savingKey === selectedPrompt.key ? 'Sauvegarde…' : 'Sauvegarder' }}
          </button>
        </div>
      </main>
    </div>

    <!-- ── Analysis Modal ─────────────────────────────────────────────────── -->
    <Transition name="modal-fade">
      <div v-if="showModal && analysisResult" class="pa-modal-overlay" @click.self="closeModal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div class="pa-modal">

          <!-- Modal Header -->
          <div class="pa-modal-header">
            <div class="pa-modal-title-row">
              <Wand2 size="20" class="pa-modal-icon" />
              <h2 id="modal-title" class="pa-modal-title">Analyse IA — <code>{{ analysisResult.key }}</code></h2>
            </div>
            <button class="pa-modal-close" @click="closeModal" aria-label="Fermer la modale">
              <X size="18" />
            </button>
          </div>

          <!-- Tabs -->
          <div class="pa-modal-tabs" role="tablist">
            <button
              role="tab"
              :aria-selected="activeModalTab === 'suggestion'"
              class="pa-tab"
              :class="{ active: activeModalTab === 'suggestion' }"
              @click="activeModalTab = 'suggestion'"
            >
              <FileText size="14" /> Prompt suggéré
            </button>
            <button
              role="tab"
              :aria-selected="activeModalTab === 'diff'"
              class="pa-tab"
              :class="{ active: activeModalTab === 'diff' }"
              @click="activeModalTab = 'diff'"
            >
              <ArrowLeftRight size="14" /> Diff avant/après
            </button>
            <button
              role="tab"
              :aria-selected="activeModalTab === 'analysis'"
              class="pa-tab"
              :class="{ active: activeModalTab === 'analysis' }"
              @click="activeModalTab = 'analysis'"
            >
              <BarChart3 size="14" /> Rapport Promptfoo
            </button>
          </div>

          <!-- Tab: Suggestion -->
          <div v-if="activeModalTab === 'suggestion'" class="pa-modal-body" role="tabpanel">
            <div class="pa-suggestion-info">
              <CheckCircle2 size="16" style="color: #10b981; flex-shrink: 0;" />
              <p>L'IA a généré un prompt optimisé. Comparez avec le diff avant d'accepter.</p>
            </div>
            <textarea
              readonly
              class="pa-textarea pa-textarea-readonly"
              :value="analysisResult.data.improved_prompt"
              rows="12"
              aria-label="Prompt amélioré par l'IA"
            ></textarea>
          </div>

          <!-- Tab: Diff -->
          <div v-if="activeModalTab === 'diff'" class="pa-modal-body" role="tabpanel">
            <div class="pa-diff-legend">
              <span class="diff-legend-item old"><span class="diff-dot"></span> Supprimé</span>
              <span class="diff-legend-item new"><span class="diff-dot"></span> Ajouté</span>
              <span class="diff-legend-item same"><span class="diff-dot"></span> Inchangé</span>
            </div>
            <div class="pa-diff-view">
              <template v-for="(line, i) in diffLines" :key="i">
                <div v-if="line.changed && line.old !== null" class="diff-line diff-removed">
                  <span class="diff-gutter">−</span>
                  <span class="diff-content">{{ line.old }}</span>
                </div>
                <div v-if="line.changed && line.new !== null" class="diff-line diff-added">
                  <span class="diff-gutter">+</span>
                  <span class="diff-content">{{ line.new }}</span>
                </div>
                <div v-if="!line.changed && line.old !== null" class="diff-line diff-same">
                  <span class="diff-gutter"> </span>
                  <span class="diff-content">{{ line.old }}</span>
                </div>
              </template>
            </div>
          </div>

          <!-- Tab: Promptfoo Report -->
          <div v-if="activeModalTab === 'analysis'" class="pa-modal-body" role="tabpanel">
            <pre class="pa-json-viewer">{{ JSON.stringify(analysisResult.data.promptfoo_report, null, 2) }}</pre>
          </div>

          <!-- Modal Footer -->
          <div class="pa-modal-footer">
            <button class="pa-btn-ghost" @click="closeModal">Annuler</button>
            <button class="pa-btn-save" @click="acceptImprovedPrompt">
              <CheckCircle2 size="16" /> Remplacer par la suggestion
            </button>
          </div>
        </div>
      </div>
    </Transition>

  </div>
</template>

<style scoped>
/* ── Root ─────────────────────────────────────────────────────────────────── */
.pa-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: calc(100vh - 64px);
  padding: 1.75rem 2rem;
  gap: 1.5rem;
  background: var(--background-alt);
  font-family: var(--font-family-base);
}

/* ── Header ───────────────────────────────────────────────────────────────── */
.pa-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-shrink: 0;
}
.pa-header-left {
  display: flex;
  align-items: center;
  gap: 0.875rem;
}
.pa-header-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #E31937 0%, #a8112a 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.3);
}
.pa-title {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
  line-height: 1.2;
}
.pa-subtitle {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  margin: 0;
}
.pa-header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.pa-dirty-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: var(--radius-full);
  padding: 0.3rem 0.75rem;
  font-size: 0.78rem;
  font-weight: 600;
}
.pulse-dot {
  animation: pulse-anim 1.5s ease-in-out infinite;
  fill: #d97706;
  color: #d97706;
}
@keyframes pulse-anim {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.pa-btn-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  border: var(--border-subtle);
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}
.pa-btn-icon:hover {
  color: var(--zenika-red);
  border-color: var(--zenika-red);
  box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1);
}

/* ── Loading Skeletons ────────────────────────────────────────────────────── */
.pa-loading {
  display: flex;
  gap: 1.5rem;
  flex: 1;
}
.pa-skeleton-sidebar {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.skeleton-item {
  height: 68px;
  border-radius: var(--radius-lg);
  background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
  background-size: 200% 100%;
  animation: pulse 1.5s infinite linear;
}
.pa-skeleton-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.5rem;
  background: white;
  border-radius: var(--radius-xl);
  border: var(--border-subtle);
}
.skeleton-row {
  height: 16px;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
  background-size: 200% 100%;
  animation: pulse 1.5s infinite linear;
}
.skeleton-row.header-row { height: 28px; width: 45%; }
.skeleton-row.short { width: 65%; }
@keyframes pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ── Empty State ──────────────────────────────────────────────────────────── */
.pa-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  color: var(--color-text-secondary);
  background: white;
  border-radius: var(--radius-xl);
  border: var(--border-subtle);
  padding: 4rem 2rem;
}
.pa-empty-icon { color: #cbd5e1; margin-bottom: 0.5rem; }
.pa-empty h3 { color: var(--color-text-primary); margin: 0; }
.pa-empty p { margin: 0; font-size: 0.9rem; }

/* ── Split View ───────────────────────────────────────────────────────────── */
.pa-split {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 1.25rem;
  flex: 1;
  min-height: 0;
  align-items: start;
}

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
.pa-sidebar {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  background: white;
  border-radius: var(--radius-xl);
  border: var(--border-subtle);
  padding: 1rem;
  box-shadow: var(--shadow-sm);
  position: sticky;
  top: 1rem;
}
.pa-search-wrapper {
  position: relative;
}
.pa-search-icon {
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-text-secondary);
  pointer-events: none;
}
.pa-search-input {
  width: 100%;
  padding: 0.55rem 0.75rem 0.55rem 2.25rem;
  background: var(--background-alt);
  border: var(--border-subtle);
  border-radius: var(--radius-md);
  font-family: var(--font-family-base);
  font-size: 0.82rem;
  color: var(--color-text-primary);
  transition: all 0.2s;
  box-sizing: border-box;
}
.pa-search-input:focus {
  outline: none;
  border-color: var(--zenika-red);
  box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1);
  background: white;
}
.pa-sidebar-count {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--color-text-secondary);
  padding: 0 0.25rem;
}
.pa-nav {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.pa-nav-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.65rem 0.75rem;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: all 0.18s;
  width: 100%;
}
.pa-nav-item:hover {
  background: var(--background-alt);
}
.pa-nav-item.active {
  background: rgba(227, 25, 55, 0.06);
  border-color: rgba(227, 25, 55, 0.2);
}
.pa-nav-item.dirty {
  border-color: rgba(245, 158, 11, 0.3);
}
.pa-nav-item-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.pa-nav-key {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pa-nav-item.active .pa-nav-key {
  color: var(--zenika-red);
}
.pa-nav-chevron {
  color: var(--color-text-secondary);
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.pa-nav-item.active .pa-nav-chevron { opacity: 1; color: var(--zenika-red); }
.pa-nav-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pa-nav-chars {
  font-size: 0.72rem;
  color: var(--color-text-secondary);
}
.pa-dirty-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f59e0b;
  display: inline-block;
}
.pa-no-results {
  text-align: center;
  padding: 1.5rem 0.5rem;
  color: var(--color-text-secondary);
  font-size: 0.82rem;
}

/* ── Editor Panel ─────────────────────────────────────────────────────────── */
.pa-editor-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  background: white;
  border-radius: var(--radius-xl);
  border: var(--border-subtle);
  padding: 1.5rem;
  box-shadow: var(--shadow-sm);
}

.pa-editor-header {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding-bottom: 1rem;
  border-bottom: var(--border-subtle);
}
.pa-editor-title-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.pa-editor-key {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}
.pa-unsaved-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: var(--radius-full);
  padding: 0.2rem 0.6rem;
  font-size: 0.72rem;
  font-weight: 600;
}
.pa-editor-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.pa-meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--background-alt);
  border: var(--border-subtle);
  border-radius: var(--radius-full);
  padding: 0.2rem 0.65rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  font-weight: 500;
}
.chip-warning {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

/* ── Textarea ─────────────────────────────────────────────────────────────── */
.pa-textarea-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid #e2e8f0;
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.pa-textarea-wrapper:focus-within {
  border-color: var(--zenika-red);
  box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1);
}
.pa-textarea {
  width: 100%;
  min-height: 380px;
  background: #0f172a;
  color: #e2e8f0;
  border: none;
  padding: 1.25rem;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.875rem;
  line-height: 1.7;
  resize: vertical;
  transition: background 0.2s;
  box-sizing: border-box;
}
.pa-textarea:focus {
  outline: none;
}
.pa-textarea-readonly {
  min-height: auto;
  background: #0f172a;
  cursor: default;
  resize: none;
}
.pa-textarea-footer {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  background: #1e293b;
  border-top: 1px solid rgba(255,255,255,0.06);
}
.pa-line-count {
  font-size: 0.72rem;
  color: #64748b;
  white-space: nowrap;
}
.pa-char-bar {
  flex: 1;
  height: 4px;
  background: rgba(255,255,255,0.07);
  border-radius: 99px;
  overflow: hidden;
}
.pa-char-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #3b82f6);
  border-radius: 99px;
  transition: width 0.3s ease;
}
.pa-char-fill.danger {
  background: linear-gradient(90deg, #f59e0b, #ef4444);
}
.pa-char-limit {
  font-size: 0.72rem;
  color: #64748b;
  white-space: nowrap;
}

/* ── Actions ──────────────────────────────────────────────────────────────── */
.pa-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding-top: 0.25rem;
}
.pa-btn-analyze,
.pa-btn-save,
.pa-btn-ghost {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1.25rem;
  border-radius: var(--radius-md);
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  font-family: var(--font-family-base);
}
.pa-btn-analyze {
  background: white;
  color: var(--color-text-primary);
  border: var(--border-subtle);
}
.pa-btn-analyze:hover:not(:disabled) {
  border-color: var(--zenika-red);
  color: var(--zenika-red);
  background: rgba(227, 25, 55, 0.04);
}
.pa-btn-analyze:disabled { opacity: 0.5; cursor: not-allowed; }

.pa-btn-save {
  background: var(--zenika-red);
  color: white;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.25);
}
.pa-btn-save:hover:not(:disabled) {
  filter: brightness(1.08);
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(227, 25, 55, 0.35);
}
.pa-btn-save:disabled { opacity: 0.45; cursor: not-allowed; transform: none; box-shadow: none; }

.pa-btn-ghost {
  background: transparent;
  color: var(--color-text-secondary);
  border: var(--border-subtle);
}
.pa-btn-ghost:hover { background: var(--background-alt); }

.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

/* ── Modal ────────────────────────────────────────────────────────────────── */
.pa-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}
.pa-modal {
  background: white;
  border-radius: var(--radius-xl);
  width: 100%;
  max-width: 860px;
  max-height: 92vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.2);
}
.pa-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  border-bottom: var(--border-subtle);
  flex-shrink: 0;
}
.pa-modal-title-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.pa-modal-icon { color: var(--zenika-red); }
.pa-modal-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}
.pa-modal-title code {
  font-family: monospace;
  font-size: 0.9em;
  background: var(--background-alt);
  padding: 0.1em 0.4em;
  border-radius: 4px;
  color: var(--zenika-red);
}
.pa-modal-close {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  border: var(--border-subtle);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--color-text-secondary);
  transition: all 0.15s;
}
.pa-modal-close:hover { background: #fef2f2; color: #ef4444; border-color: #fecaca; }

.pa-modal-tabs {
  display: flex;
  gap: 0;
  border-bottom: var(--border-subtle);
  flex-shrink: 0;
  padding: 0 1.5rem;
}
.pa-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0.75rem 1rem;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  font-family: var(--font-family-base);
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  transition: all 0.2s;
  margin-bottom: -1px;
}
.pa-tab:hover { color: var(--color-text-primary); }
.pa-tab.active {
  color: var(--zenika-red);
  border-bottom-color: var(--zenika-red);
}

.pa-modal-body {
  padding: 1.25rem 1.5rem;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* suggestion tab */
.pa-suggestion-info {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  background: rgba(16, 185, 129, 0.07);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: var(--radius-md);
  padding: 0.75rem 1rem;
  font-size: 0.85rem;
  color: #065f46;
}
.pa-suggestion-info p { margin: 0; }

/* diff tab */
.pa-diff-legend {
  display: flex;
  gap: 1.25rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}
.diff-legend-item { display: flex; align-items: center; gap: 5px; }
.diff-legend-item.old .diff-dot { background: #fecaca; }
.diff-legend-item.new .diff-dot { background: #bbf7d0; }
.diff-legend-item.same .diff-dot { background: #e2e8f0; }
.diff-dot { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }

.pa-diff-view {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.8rem;
  line-height: 1.6;
  border: var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
  overflow-y: auto;
  max-height: 340px;
}
.diff-line {
  display: flex;
  align-items: baseline;
  gap: 0;
  padding: 0.1rem 0;
}
.diff-gutter {
  width: 28px;
  text-align: center;
  flex-shrink: 0;
  font-weight: 700;
  user-select: none;
}
.diff-content {
  flex: 1;
  padding: 0 0.75rem 0 0;
  white-space: pre-wrap;
  word-break: break-word;
}
.diff-removed { background: #fef2f2; }
.diff-removed .diff-gutter { color: #ef4444; background: #fee2e2; }
.diff-added { background: #f0fdf4; }
.diff-added .diff-gutter { color: #10b981; background: #dcfce7; }
.diff-same { background: white; }
.diff-same .diff-gutter { color: #94a3b8; background: #f8fafc; }

/* json report */
.pa-json-viewer {
  background: #0f172a;
  color: #94a3b8;
  padding: 1rem;
  border-radius: var(--radius-md);
  font-size: 0.8rem;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  flex: 1;
}

.pa-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: var(--border-subtle);
  flex-shrink: 0;
}

/* ── Modal Transition ─────────────────────────────────────────────────────── */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.25s ease;
}
.modal-fade-enter-active .pa-modal,
.modal-fade-leave-active .pa-modal {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s ease;
}
.modal-fade-enter-from { opacity: 0; }
.modal-fade-enter-from .pa-modal { transform: translateY(16px) scale(0.97); opacity: 0; }
.modal-fade-leave-to { opacity: 0; }
.modal-fade-leave-to .pa-modal { transform: translateY(8px) scale(0.98); opacity: 0; }

/* ── Responsive ───────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .pa-root { padding: 1rem; }
  .pa-split {
    grid-template-columns: 1fr;
  }
  .pa-sidebar {
    position: static;
  }
  .pa-textarea { min-height: 220px; }
  .pa-header { flex-wrap: wrap; }
}
</style>
