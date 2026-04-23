<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import CompetencyNode from '../components/CompetencyNode.vue'
import StarRating from '../components/StarRating.vue'
import { Network, RefreshCw, User, X, ExternalLink, Users, BarChart2, Brain, UserCheck } from 'lucide-vue-next'

// ── Types ──────────────────────────────────────────────────────────────────
interface Evaluation {
  user_id: number
  ai_score: number | null
  user_score: number | null
  ai_justification: string | null
}
interface UserInfo {
  id: number
  full_name: string
  email: string
  role: string
  picture_url?: string
}

// ── State ──────────────────────────────────────────────────────────────────
const competencies = ref<any[]>([])
const loading = ref(true)
const error = ref('')

// Sidepanel
const isSidepanelOpen = ref(false)
const selectedCompetency = ref<any>(null)
const associatedUsers = ref<UserInfo[]>([])
const totalUserCount = ref(0)
const isLoadingUsers = ref(false)

// Evaluations pour la compétence sélectionnée
const evaluations = ref<Evaluation[]>([])
const isLoadingEvals = ref(false)

// Stats globales (calculées une seule fois à l'ouverture d'une feuille)
const avgAiScore = computed(() => {
  const scored = evaluations.value.filter(e => e.ai_score !== null)
  if (!scored.length) return null
  return scored.reduce((s, e) => s + (e.ai_score ?? 0), 0) / scored.length
})

const avgUserScore = computed(() => {
  const scored = evaluations.value.filter(e => e.user_score !== null)
  if (!scored.length) return null
  return scored.reduce((s, e) => s + (e.user_score ?? 0), 0) / scored.length
})

const scoredCount = computed(() => evaluations.value.filter(e => e.ai_score !== null).length)
const selfEvalCount = computed(() => evaluations.value.filter(e => e.user_score !== null).length)

// Map userId → evaluation pour le rendu dans la liste des users
const evalByUser = computed(() => {
  const map: Record<number, Evaluation> = {}
  evaluations.value.forEach(e => { map[e.user_id] = e })
  return map
})

// Barre de distribution des scores IA (buckets 0-1, 1-2, 2-3, 3-4, 4-5)
const scoreDistribution = computed(() => {
  const buckets = [0, 0, 0, 0, 0]
  evaluations.value.forEach(e => {
    if (e.ai_score === null) return
    const idx = Math.min(Math.floor(e.ai_score), 4)
    buckets[idx]++
  })
  const max = Math.max(...buckets, 1)
  return buckets.map((count, i) => ({
    label: `${i}–${i + 1}★`,
    count,
    pct: Math.round((count / max) * 100)
  }))
})

// ── Actions ────────────────────────────────────────────────────────────────
const onSelectLeaf = async (node: any) => {
  selectedCompetency.value = node
  isSidepanelOpen.value = true
  isLoadingUsers.value = true
  isLoadingEvals.value = true
  associatedUsers.value = []
  evaluations.value = []
  totalUserCount.value = 0

  try {
    // 1. User IDs associés à la compétence
    const userIdsRes = await axios.get(`/api/competencies/${node.id}/users`)
    const allUserIds: number[] = userIdsRes.data || []
    totalUserCount.value = allUserIds.length

    // 2. Détails utilisateurs (max 15)
    if (allUserIds.length > 0) {
      const topIds = allUserIds.slice(0, 15)
      const usersRes = await axios.post(`/api/users/bulk`, topIds)
      associatedUsers.value = usersRes.data || []
    }
  } catch (err) {
    console.error('Failed to fetch users', err)
  } finally {
    isLoadingUsers.value = false
  }

  // 3. Récupérer les évaluations de chaque utilisateur pour cette compétence
  if (associatedUsers.value.length > 0) {
    try {
      const userIds = associatedUsers.value.map(u => u.id)
      const res = await axios.post('/api/competencies/evaluations/batch/users', {
        competency_id: node.id,
        user_ids: userIds
      })
      const evalsDict = res.data.evaluations || {}
      evaluations.value = Object.values(evalsDict)
    } catch (err) {
      console.error('Failed to fetch evaluations batch', err)
      // Fallback in case of error
      evaluations.value = associatedUsers.value.map(u => ({
        user_id: u.id, competency_id: node.id, competency_name: node.name,
        ai_score: null, user_score: null, ai_justification: null
      }))
    } finally {
      isLoadingEvals.value = false
    }
  } else {
    isLoadingEvals.value = false
  }
}

const closeSidepanel = () => {
  isSidepanelOpen.value = false
}

const fetchCompetencies = async () => {
  loading.value = true
  error.value = ''
  try {
    const limit = 50
    const firstRes = await axios.get(`/api/competencies/?skip=0&limit=${limit}`)
    let allItems = firstRes.data.items || []
    const total = firstRes.data.total || 0
    if (total > limit) {
      const promises = []
      for (let skip = limit; skip < total; skip += limit) {
        promises.push(axios.get(`/api/competencies/?skip=${skip}&limit=${limit}`))
      }
      const responses = await Promise.all(promises)
      responses.forEach(res => { allItems = allItems.concat(res.data.items || []) })
    }
    competencies.value = allItems
  } catch (err: any) {
    error.value = "Impossible de charger l'arbre des compétences."
    console.error(err)
  } finally {
    loading.value = false
  }
}

// Couleur selon score
function scoreColor(score: number | null): string {
  if (score === null) return '#64748b'
  if (score >= 4) return '#22c55e'
  if (score >= 3) return '#f59e0b'
  if (score >= 2) return '#f97316'
  return '#ef4444'
}

onMounted(() => { fetchCompetencies() })
</script>

<template>
  <div class="competencies-container fade-in">
    <div class="header-section">
      <div class="title-wrapper">
        <Network class="icon-title" size="32" />
        <h2>Référentiel de Compétences</h2>
      </div>
      <p class="subtitle">Arborescence globale des expertises · Cliquez sur une feuille pour voir l'état des lieux Zenika.</p>
    </div>

    <div class="tree-card glass-panel">
      <div class="card-header">
        <h3>Explorateur Stratégique</h3>
        <button class="icon-btn" @click="fetchCompetencies" :disabled="loading" title="Actualiser l'arbre" aria-label="Actualiser l'arbre">
          <RefreshCw size="18" :class="{ 'spin': loading }" />
        </button>
      </div>

      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>Récupération du graphe de compétences...</span>
      </div>
      <div v-else-if="error" class="error-msg">{{ error }}</div>
      <div v-else-if="competencies.length === 0" class="empty-state">Aucune compétence n'est actuellement définie.</div>
      <div v-else class="tree-view">
        <CompetencyNode
          v-for="rootNode in competencies"
          :key="rootNode.id"
          :node="rootNode"
          :depth="0"
          @select-leaf="onSelectLeaf"
        />
      </div>
    </div>

    <!-- Sidepanel (Drawer) -->
    <Transition name="slide-panel">
      <div v-if="isSidepanelOpen" class="sidepanel-overlay" @click.self="closeSidepanel">
        <div class="sidepanel-content glass-panel" @click.stop role="dialog" :aria-label="`Détail compétence : ${selectedCompetency?.name}`">

          <!-- Header -->
          <div class="sidepanel-header">
            <div class="header-main">
              <div class="comp-icon"><Network size="20" /></div>
              <div class="comp-title">
                <h3>{{ selectedCompetency?.name }}</h3>
                <div class="side-aliases" v-if="selectedCompetency?.aliases">
                  <span v-for="alias in selectedCompetency.aliases.split(',')" :key="alias" class="side-alias-badge">
                    {{ alias.trim() }}
                  </span>
                </div>
                <span class="comp-id">#{{ selectedCompetency?.id }}</span>
              </div>
            </div>
            <button class="close-btn" @click="closeSidepanel" aria-label="Fermer">
              <X size="20" />
            </button>
          </div>

          <div class="sidepanel-body">

            <!-- Stats banner -->
            <div class="stats-row">
              <div class="stat-chip">
                <Users size="15" />
                <span><strong>{{ totalUserCount }}</strong> consultant(s)</span>
              </div>
              <div class="stat-chip ai" v-if="avgAiScore !== null">
                <Brain size="15" />
                <span>Moy. IA <strong>{{ avgAiScore.toFixed(1) }}</strong>/5</span>
                <span class="stat-dot" :style="{ background: scoreColor(avgAiScore) }"></span>
              </div>
              <div class="stat-chip user" v-if="avgUserScore !== null">
                <UserCheck size="15" />
                <span>Moy. auto <strong>{{ avgUserScore.toFixed(1) }}</strong>/5</span>
              </div>
            </div>

            <!-- Distribution des scores IA -->
            <div v-if="scoredCount > 0 && !isLoadingEvals" class="distribution-block">
              <p class="section-label">
                <Brain size="13" />
                Distribution scores Gemini ({{ scoredCount }}/{{ totalUserCount }} évalués)
              </p>
              <div class="distrib-bars">
                <div v-for="bucket in scoreDistribution" :key="bucket.label" class="distrib-row">
                  <span class="bucket-label">{{ bucket.label }}</span>
                  <div class="bar-track">
                    <div
                      class="bar-fill"
                      :style="{ width: bucket.pct + '%', background: bucket.count > 0 ? '#f59e0b' : '#e2e8f0' }"
                    />
                  </div>
                  <span class="bucket-count">{{ bucket.count }}</span>
                </div>
              </div>
              <p class="section-label auto-eval-info" v-if="selfEvalCount > 0">
                <UserCheck size="13" />
                {{ selfEvalCount }} auto-évaluation(s) disponible(s)
              </p>
            </div>

            <!-- Loading evals -->
            <div v-if="isLoadingUsers || isLoadingEvals" class="fetching-state">
              <div class="pulse-spinner"></div>
              <p>Récupération des profils et scores...</p>
            </div>

            <!-- No users -->
            <div v-else-if="associatedUsers.length === 0" class="no-users">
              <User size="32" class="opacity-20" />
              <p>Aucun utilisateur associé à cette compétence.</p>
            </div>

            <!-- Liste des consultants avec leurs scores -->
            <div v-else class="users-list">
              <p class="list-hint" v-if="totalUserCount > 15">Affichage des 15 premières entrées :</p>

              <div v-for="user in associatedUsers" :key="user.id" class="user-card">
                <div class="user-avatar">
                  <img v-if="user.picture_url" :src="user.picture_url" :alt="user.full_name">
                  <User v-else size="18" />
                </div>
                <div class="user-info">
                  <span class="user-name">{{ user.full_name }}</span>
                  <div class="user-scores">
                    <!-- Score IA -->
                    <div class="score-badge ai-badge" v-if="evalByUser[user.id]?.ai_score !== null && evalByUser[user.id]?.ai_score !== undefined" :title="evalByUser[user.id]?.ai_justification ?? ''">
                      <Brain size="10" />
                      <StarRating :modelValue="evalByUser[user.id]?.ai_score ?? 0" :readonly="true" size="sm" />
                      <span class="score-val">{{ evalByUser[user.id]?.ai_score?.toFixed(1) }}</span>
                    </div>
                    <div class="score-badge empty-badge" v-else>
                      <Brain size="10" />
                      <span class="score-val muted">—</span>
                    </div>

                    <!-- Score utilisateur -->
                    <div class="score-badge user-badge" v-if="evalByUser[user.id]?.user_score !== null && evalByUser[user.id]?.user_score !== undefined">
                      <UserCheck size="10" />
                      <StarRating :modelValue="evalByUser[user.id]?.user_score ?? 0" :readonly="true" size="sm" />
                      <span class="score-val">{{ evalByUser[user.id]?.user_score?.toFixed(1) }}</span>
                    </div>
                  </div>
                </div>
                <RouterLink :to="{ name: 'user-detail', params: { id: user.id } }" class="profile-link" title="Voir le profil" aria-label="Voir le profil">
                  <ExternalLink size="14" />
                </RouterLink>
              </div>
            </div>

          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.competencies-container {
  max-width: 1000px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header-section {
  text-align: center;
  margin-bottom: 40px;
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
  color: #1A1A1A;
  letter-spacing: -1px;
}

.icon-title { color: #E31937; }

.subtitle {
  color: #555;
  font-size: 17px;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(227, 25, 55, 0.08);
  overflow: hidden;
}

.tree-card { padding: 0; }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 30px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(20, 20, 20, 0.6);
}

h3 {
  font-size: 18px;
  font-weight: 600;
  color: #1A1A1A;
  margin: 0;
}

.tree-view {
  padding: 20px 30px 40px 30px;
  min-height: 300px;
}

.loading-state, .empty-state, .error-msg {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: #888;
  text-align: center;
}

.error-msg { color: #ff5252; }

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(227, 25, 55, 0.2);
  border-top-color: #E31937;
  border-radius: 50%;
  animation: spin 1s infinite linear;
  margin-bottom: 16px;
}

.icon-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #ccc;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}
.icon-btn:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }

.spin { animation: spin 1s infinite linear; }

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.fade-in { animation: fadeIn 0.4s ease-out; }

/* ── Sidepanel ─────────────────────────────────────────────────────────── */
.slide-panel-enter-active, .slide-panel-leave-active {
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.slide-panel-enter-from, .slide-panel-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.sidepanel-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.sidepanel-content {
  width: 440px;
  max-width: 92vw;
  height: 100%;
  border-left: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 20px 0 0 20px;
  display: flex;
  flex-direction: column;
  animation: slideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }

.sidepanel-header {
  padding: 20px 24px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.header-main { display: flex; align-items: flex-start; gap: 12px; }

.comp-icon {
  background: rgba(227, 25, 55, 0.1);
  color: #E31937;
  padding: 8px;
  border-radius: 8px;
  margin-top: 2px;
}

.comp-title h3 { margin: 0; font-size: 1.05rem; font-weight: 700; color: #1e293b; }
.comp-id { font-size: 0.72rem; font-family: monospace; color: #E31937; font-weight: 600; display: block; }

.side-aliases { display: flex; flex-wrap: wrap; gap: 4px; margin: 4px 0; }
.side-alias-badge {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  background: rgba(227, 25, 55, 0.05); color: #E31937;
  padding: 2px 7px; border-radius: 4px; border: 1px solid rgba(227, 25, 55, 0.1);
}

.close-btn {
  background: #f1f5f9; border: none; width: 34px; height: 34px;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: #64748b; transition: all 0.2s; flex-shrink: 0;
}
.close-btn:hover { background: #e2e8f0; color: #0f172a; }

.sidepanel-body { flex: 1; padding: 20px 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 1rem; }

/* ── Stats row ─────────────────────────────────────────────────────────── */
.stats-row { display: flex; flex-wrap: wrap; gap: 8px; }

.stat-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 500;
  color: #374151;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}
.stat-chip.ai { background: rgba(245, 158, 11, 0.08); border-color: rgba(245, 158, 11, 0.3); color: #92400e; }
.stat-chip.user { background: rgba(34, 197, 94, 0.08); border-color: rgba(34, 197, 94, 0.3); color: #166534; }

.stat-dot { width: 8px; height: 8px; border-radius: 50%; }

/* ── Distribution ──────────────────────────────────────────────────────── */
.distribution-block {
  background: #fafafa;
  border: 1px solid #f1f5f9;
  border-radius: 12px;
  padding: 14px 16px;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  margin: 0 0 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.auto-eval-info { margin: 10px 0 0; color: #22c55e; }

.distrib-bars { display: flex; flex-direction: column; gap: 6px; }

.distrib-row { display: flex; align-items: center; gap: 8px; }

.bucket-label {
  font-size: 0.7rem;
  font-family: monospace;
  color: #94a3b8;
  width: 36px;
  flex-shrink: 0;
}

.bar-track {
  flex: 1;
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

.bucket-count {
  font-size: 0.7rem;
  font-weight: 600;
  color: #64748b;
  width: 20px;
  text-align: right;
  flex-shrink: 0;
}

/* ── Fetching ──────────────────────────────────────────────────────────── */
.fetching-state {
  display: flex; flex-direction: column; align-items: center;
  gap: 14px; padding: 40px 0; color: #64748b;
}
.pulse-spinner {
  width: 36px; height: 36px; border-radius: 50%; background: #E31937;
  animation: pulseScale 1.5s infinite ease-in-out;
}
@keyframes pulseScale {
  0% { transform: scale(0.8); opacity: 0.5; }
  50% { transform: scale(1.1); opacity: 1; }
  100% { transform: scale(0.8); opacity: 0.5; }
}

.no-users { text-align: center; color: #94a3b8; padding: 40px 0; }
.no-users p { margin-top: 10px; font-size: 0.9rem; }

/* ── Users list ────────────────────────────────────────────────────────── */
.users-list { display: flex; flex-direction: column; gap: 8px; }

.list-hint { font-size: 0.78rem; color: #64748b; font-style: italic; margin: 0 0 4px; }

.user-card {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  transition: all 0.2s;
  gap: 10px;
}
.user-card:hover { border-color: #E31937; box-shadow: 0 2px 10px rgba(227, 25, 55, 0.06); }

.user-avatar {
  width: 36px; height: 36px; border-radius: 10px;
  background: #f1f5f9; display: flex; align-items: center; justify-content: center;
  overflow: hidden; flex-shrink: 0; color: #94a3b8;
}
.user-avatar img { width: 100%; height: 100%; object-fit: cover; }

.user-info { flex: 1; min-width: 0; }

.user-name { font-weight: 600; font-size: 0.88rem; color: #1e293b; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.user-scores { display: flex; align-items: center; gap: 8px; margin-top: 3px; flex-wrap: wrap; }

.score-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 0.68rem;
  padding: 2px 6px;
  border-radius: 6px;
}
.score-badge.ai-badge { background: rgba(245, 158, 11, 0.08); color: #92400e; }
.score-badge.user-badge { background: rgba(34, 197, 94, 0.08); color: #166534; }
.score-badge.empty-badge { background: #f8fafc; color: #94a3b8; }

.score-val { font-weight: 700; font-size: 0.72rem; }
.score-val.muted { color: #cbd5e1; }

.profile-link {
  color: #94a3b8; padding: 6px; border-radius: 7px;
  transition: all 0.2s; flex-shrink: 0; display: flex; align-items: center;
}
.profile-link:hover { background: #f1f5f9; color: #E31937; }

.opacity-20 { opacity: 0.2; }
</style>
