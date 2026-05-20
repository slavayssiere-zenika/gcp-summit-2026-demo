<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
// parsePaginated bypass (endpoints fetched here are not paginated: extraction quality evaluations/statistics)
import { useI18n } from 'vue-i18n'
import { ShieldCheck, Search, ChevronLeft, ChevronRight, RotateCw, Info } from 'lucide-vue-next'
import { authService } from '../services/auth'
import PageHeader from '../components/ui/PageHeader.vue'

const { t } = useI18n()

const isLoading = ref(false)
const error = ref('')
const items = ref<any[]>([])
const total = ref(0)
const skip = ref(0)
const limit = ref(50)
const searchQuery = ref('')
const sortDesc = ref(true)
const currentTab = ref('calculated')

const fetchScores = async () => {
  isLoading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/cv/extraction-scores', {
      params: {
        limit: limit.value,
        skip: skip.value,
        sort_desc: sortDesc.value,
        search: searchQuery.value || undefined,
        status: currentTab.value
      },
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    
    items.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e: any) {
    error.value = e.response?.data?.detail || "Erreur de récupération des scores"
  } finally {
    isLoading.value = false
  }
}

const nextPage = () => {
  if (skip.value + limit.value < total.value) {
    skip.value += limit.value
    fetchScores()
  }
}

const prevPage = () => {
  if (skip.value > 0) {
    skip.value = Math.max(0, skip.value - limit.value)
    fetchScores()
  }
}

const toggleSort = () => {
  sortDesc.value = !sortDesc.value
  skip.value = 0
  fetchScores()
}

const triggerSearch = () => {
  skip.value = 0
  fetchScores()
}

const changeTab = (tab: string) => {
  if (currentTab.value !== tab) {
    currentTab.value = tab
    skip.value = 0
    fetchScores()
  }
}

const reanalyzingId = ref<number | null>(null)

const triggerReanalyze = async (userId: number) => {
  if (!confirm(`Relancer l'extraction et l'analyse complète pour ce profil (ID: ${userId}) ?`)) return
  
  reanalyzingId.value = userId
  error.value = ''
  try {
    await axios.post('/api/cv/reanalyze', null, {
      params: { user_id: userId },
      headers: { Authorization: `Bearer ${authService.state.token}` }
    })
    // Optionally fetch scores or just notify success
    alert('Ré-importation planifiée avec succès. Les résultats apparaîtront d\'ici quelques minutes.')
  } catch (e: any) {
    error.value = e.response?.data?.detail || "Erreur lors de la ré-analyse"
  } finally {
    reanalyzingId.value = null
  }
}

onMounted(() => {
  fetchScores()
})
</script>

<template>
  <div class="admin-wrapper fade-in">
    <PageHeader
      :title="t('extractionquality.title')"
      :subtitle="t('extractionquality.subtitle')"
      :icon="ShieldCheck"
      :breadcrumb="[
        { label: 'Admin Hub', to: '/admin' },
        { label: 'Qualité Extraction' }
      ]"
    />

    <div class="error-panel fade-in-up" v-if="error">
       <strong>{{ t('extractionquality.error_prefix') }}</strong> {{ error }}
    </div>

    <div class="glass-panel mt-4">
      <div class="info-panel mb-4">
        <Info size="18" class="info-icon" />
        <div class="info-text">
          <strong>{{ t('extractionquality.score_help') }}</strong><br/>
          Il représente la similarité sémantique (Cosinus) entre le texte brut original du CV et les données structurées extraites par l'IA. 
          Un score élevé (≥ 75%) indique que l'IA a fidèlement capturé le contenu original sans perte d'information ni hallucination.
        </div>
      </div>

      <div class="tabs-container mb-4">
        <button 
          class="tab-button" 
          :class="{ active: currentTab === 'calculated' }" 
          @click="changeTab('calculated')">
          Scores Calculés
        </button>
        <button 
          class="tab-button" 
          :class="{ active: currentTab === 'uncalculated' }" 
          @click="changeTab('uncalculated')">
          Non Calculés
        </button>
      </div>

      <div class="panel-header d-flex-between" style="gap: 1rem; flex-wrap: wrap;">
        <div style="display: flex; gap: 1rem; align-items: center; flex: 1;">
          <div class="search-box">
            <Search size="16" class="search-icon" />
            <input 
              id="extraction-search"
              type="text" 
              v-model="searchQuery" 
              @keyup.enter="triggerSearch" 
              :placeholder="t('extractionquality.search_placeholder')"
              class="search-input"
              aria-label="Recherche candidat"
            />
          </div>
          <button @click="triggerSearch" class="action-btn-secondary" :disabled="isLoading">
            Chercher
          </button>
        </div>
        
        <div style="display: flex; gap: 1rem; align-items: center;">
          <button @click="fetchScores" class="action-btn-secondary" :disabled="isLoading" aria-label="Rafraîchir les scores">
            <RotateCw :class="{ 'spin': isLoading }" size="16" /> Rafraîchir
          </button>
        </div>
      </div>

      <div class="candidate-table-wrapper">
        <table class="candidate-table">
          <thead>
            <tr>
              <th>{{ t('extractionquality.col_id') }}</th>
              <th>{{ t('extractionquality.col_candidate') }}</th>
              <th>{{ t('extractionquality.col_agency') }}</th>
              <th @click="currentTab === 'calculated' && toggleSort()" :style="{ cursor: currentTab === 'calculated' ? 'pointer' : 'default' }" title="Trier par score">
                Score Fiabilité 
                <template v-if="currentTab === 'calculated'">
                  <span v-if="sortDesc">↓</span><span v-else>↑</span>
                </template>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="items.length === 0 && !isLoading">
              <td colspan="4" class="empty-state-cell">{{ t('extractionquality.empty') }}</td>
            </tr>
            <template v-for="c in items" :key="c.id">
              <tr>
                <td class="id-cell">
                  <RouterLink :to="'/user/' + c.user_id" class="text-link">{{ c.user_id }}</RouterLink>
                </td>
                <td>
                  <div class="user-info">
                    <strong>{{ c.full_name || '—' }}</strong>
                    <br/><span class="text-xs text-muted">{{ c.email || '—' }}</span>
                  </div>
                </td>
                <td>
                  <span v-if="c.source_tag" class="tag-badge">{{ c.source_tag }}</span>
                  <span v-else class="text-muted">—</span>
                  <br/>
                  <span class="text-xs" style="color: #64748b; margin-top: 4px; display: inline-block;">{{ c.current_role || 'Rôle non défini' }}</span>
                </td>
                <td>
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <div v-if="currentTab === 'calculated'" class="score-badge" :class="c.extraction_reliability_score >= 75 ? 'score-good' : 'score-bad'">
                      {{ c.extraction_reliability_score }}%
                    </div>
                    <div v-else class="score-badge" style="background: #f1f5f9; color: #64748b;">
                      N/A
                    </div>
                    <button class="action-btn-secondary btn-sm" @click="triggerReanalyze(c.user_id)" :disabled="reanalyzingId === c.user_id" :aria-label="t('extractionquality.reimport')">
                      <RotateCw v-if="reanalyzingId === c.user_id" class="spin" size="14" />
                      <span v-else>{{ t('extractionquality.reimport') }}</span>
                    </button>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      
      <div class="pagination" v-if="total > 0">
        <div class="pagination-info">
          Affichage de {{ skip + 1 }} à {{ Math.min(skip + limit, total) }} sur {{ total }}
        </div>
        <div class="pagination-controls">
          <button @click="prevPage" :disabled="skip === 0 || isLoading" class="action-btn-secondary" aria-label="Page précédente">
            <ChevronLeft size="16" /> Précédent
          </button>
          <button @click="nextPage" :disabled="skip + limit >= total || isLoading" class="action-btn-secondary" aria-label="Page suivante">
            Suivant <ChevronRight size="16" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-wrapper { max-width: 1100px; margin: 0 auto; padding: 2rem; }

.glass-panel { background: rgba(255, 255, 255, 0.5); backdrop-filter: blur(20px); border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.4); padding: 2rem; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04); }
.panel-header { margin-bottom: 1.5rem; }
.d-flex-between { display: flex; justify-content: space-between; align-items: center; }

.action-btn-secondary { background: white; border: 1px solid #e2e8f0; padding: 0.5rem 1rem; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 8px; font-weight: 500; color: #475569; }
.action-btn-secondary:hover:not(:disabled) { background: #f8fafc; }
.action-btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm { padding: 0.25rem 0.5rem; font-size: 0.8rem; border-radius: 6px; }

.search-box { position: relative; flex: 1; max-width: 400px; }
.search-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: #94a3b8; }
.search-input { width: 100%; padding: 0.6rem 0.6rem 0.6rem 2.2rem; border-radius: 8px; border: 1px solid #cbd5e1; outline: none; }
.search-input:focus { border-color: var(--zenika-red); box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1); }

.error-panel { margin-top: 2rem; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); padding: 1.5rem; border-radius: 12px; color: #b91c1c; }

.candidate-table-wrapper { overflow-x: auto; border-radius: 10px; border: 1px solid #e2e8f0; background: white; }
.candidate-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.candidate-table th { padding: 12px 16px; text-align: left; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; background: #f8fafc; border-bottom: 1px solid #e2e8f0; user-select: none; }
.candidate-table td { padding: 12px 16px; border-bottom: 1px solid #f1f5f9; color: #1e293b; vertical-align: middle; }
.candidate-table tr:last-child td { border-bottom: none; }
.candidate-table tr:hover td { background: #f8fafc; }

.empty-state-cell { text-align: center; padding: 3rem !important; color: #64748b; font-style: italic; }

.text-link { color: inherit; text-decoration: none; font-weight: 600; }
.text-link:hover { color: var(--zenika-red); text-decoration: underline; }

.user-info strong { color: #0f172a; }
.text-xs { font-size: 0.8rem; }
.text-muted { color: #64748b; }

.tag-badge { background: rgba(227, 25, 55, 0.05); padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: 500; color: #334155; display: inline-block; }

.score-badge { display: inline-flex; align-items: center; justify-content: center; padding: 4px 10px; border-radius: 20px; font-size: 0.85rem; font-weight: 600; }
.score-good { background: rgba(16, 185, 129, 0.1); color: #059669; }
.score-bad { background: rgba(239, 68, 68, 0.1); color: #dc2626; }

.pagination { display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid rgba(255, 255, 255, 0.4); }
.pagination-info { font-size: 0.85rem; color: #64748b; }
.pagination-controls { display: flex; gap: 0.5rem; }

.spin { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }
.fade-in { animation: fadeIn 0.4s ease forwards; }
.fade-in-up { animation: fadeInUp 0.5s ease forwards; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
.info-panel { display: flex; gap: 12px; background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.2); padding: 16px; border-radius: 12px; color: #1e3a8a; font-size: 0.85rem; line-height: 1.5; }
.info-icon { color: #2563eb; flex-shrink: 0; margin-top: 2px; }
.info-text strong { color: #1d4ed8; font-weight: 600; display: inline-block; margin-bottom: 4px; }
.mb-4 { margin-bottom: 1.5rem; }

.tabs-container { display: flex; gap: 8px; border-bottom: 1px solid #e2e8f0; padding-bottom: 0px; }
.tab-button { background: none; border: none; padding: 10px 16px; font-size: 0.95rem; font-weight: 600; color: #64748b; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
.tab-button:hover { color: #1e293b; }
.tab-button.active { color: var(--zenika-red); border-bottom: 2px solid var(--zenika-red); }

.mt-4 { margin-top: 2rem; }
</style>
