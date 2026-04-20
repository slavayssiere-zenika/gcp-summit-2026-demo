<template>
  <div class="eval-panel">
    <!-- Header -->
    <div class="eval-header">
      <div class="eval-title-row">
        <Award :size="22" class="eval-icon" />
        <h3>Évaluation des compétences</h3>
      </div>
      <div class="eval-actions">
        <button
          class="btn-primary"
          :disabled="isTriggering"
          @click="triggerAiScoring"
          aria-label="Lancer l'évaluation IA sur toutes les compétences"
        >
          <Zap :size="15" />
          <span>{{ isTriggering ? 'Calcul en cours…' : 'Évaluation IA' }}</span>
        </button>
        <button class="btn-ghost" @click="fetchEvaluations" :disabled="isLoading" aria-label="Rafraîchir">
          <RefreshCw :size="15" :class="{ spin: isLoading }" />
        </button>
      </div>
    </div>

    <p class="eval-subtitle">
      Compétences feuilles · 🤖 = note Gemini · cliquez les ⭐ pour vous auto-évaluer
    </p>

    <!-- Loading skeleton -->
    <div v-if="isLoading" class="eval-skeleton">
      <div v-for="i in 5" :key="i" class="skeleton-row" />
    </div>

    <!-- Empty state -->
    <div v-else-if="!evaluations.length" class="eval-empty">
      <BrainCircuit :size="36" />
      <p>Aucune compétence feuille assignée.</p>
    </div>

    <!-- Table -->
    <div v-else class="eval-table-wrap">
      <table class="eval-table" aria-label="Tableau d'évaluation des compétences">
        <thead>
          <tr>
            <th>Compétence</th>
            <th>🤖 IA</th>
            <th>👤 Mon évaluation</th>
            <th v-if="!readonly" class="th-coach">Coach</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="ev in evaluations"
            :key="ev.competency_id"
            class="eval-row"
            :class="{ 'saving': savingIds.has(ev.competency_id), 'saved': savedIds.has(ev.competency_id) }"
          >
            <!-- Nom de la compétence -->
            <td class="comp-name">{{ ev.competency_name }}</td>

            <!-- Note IA -->
            <td class="score-cell">
              <div v-if="ev.ai_score !== null" class="score-with-tip">
                <StarRating :modelValue="ev.ai_score" :readonly="true" size="sm" />
                <span class="score-num">{{ ev.ai_score?.toFixed(1) }}</span>
                <button
                  v-if="ev.ai_justification"
                  class="tip-btn"
                  :title="ev.ai_justification"
                  :aria-label="`Justification Gemini : ${ev.ai_justification}`"
                >
                  <Info :size="13" />
                </button>
              </div>
              <span v-else class="score-pending">—</span>
            </td>

            <!-- Note utilisateur — cliquable inline, save auto -->
            <td class="score-cell user-score-cell">
              <div class="user-score-row">
                <template v-if="!readonly">
                  <StarRating
                    :modelValue="ev.user_score ?? 0"
                    size="sm"
                    :readonly="false"
                    @update:modelValue="(val) => onUserScoreChange(ev, val)"
                    :aria-label="`Évaluer ${ev.competency_name}`"
                  />
                  <span class="score-num score-num--user">
                    {{ ev.user_score !== null ? ev.user_score.toFixed(1) : '–' }}
                  </span>
                  <!-- Feedback inline: spinner ou checkmark -->
                  <span v-if="savingIds.has(ev.competency_id)" class="feedback-icon saving-icon" aria-label="Enregistrement…">
                    <Loader2 :size="13" class="spin-anim" />
                  </span>
                  <span v-else-if="savedIds.has(ev.competency_id)" class="feedback-icon saved-icon" aria-label="Enregistré">
                    <Check :size="13" />
                  </span>
                </template>
                <template v-else>
                  <div v-if="ev.user_score !== null" class="score-with-tip">
                    <StarRating :modelValue="ev.user_score" :readonly="true" size="sm" />
                    <span class="score-num">{{ ev.user_score?.toFixed(1) }}</span>
                  </div>
                  <span v-else class="score-pending">—</span>
                </template>
              </div>
            </td>

            <!-- Coach uniquement -->
            <td v-if="!readonly" class="action-cell">
              <button
                class="coach-btn"
                @click="openCoach(ev)"
                :aria-label="`Coaching CV pour ${ev.competency_name}`"
                title="Coaching CV"
              >
                <MessageSquare :size="14" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Coach Side-Drawer -->
    <Teleport to="body">
      <div v-if="coachDrawerOpen" class="coach-overlay" @click.self="coachDrawerOpen = false">
        <div class="coach-drawer glass-panel" role="dialog" :aria-label="`Coaching CV — ${coachingComp?.competency_name}`">
          <div class="drawer-header">
            <div class="drawer-title">
              <MessageSquare :size="18" />
              <span>Coach CV — <strong>{{ coachingComp?.competency_name }}</strong></span>
            </div>
            <button class="close-btn" @click="coachDrawerOpen = false" aria-label="Fermer">
              <X :size="18" />
            </button>
          </div>

          <div class="drawer-scores">
            <div class="dscore-item">
              <span class="dscore-label">🤖 Gemini</span>
              <StarRating :modelValue="coachingComp?.ai_score ?? 0" :readonly="true" size="sm" />
            </div>
            <div class="dscore-item">
              <span class="dscore-label">👤 Vous</span>
              <StarRating :modelValue="coachingComp?.user_score ?? 0" :readonly="true" size="sm" />
            </div>
          </div>

          <div v-if="coachingComp?.ai_justification" class="drawer-justification">
            <span class="just-label">Analyse Gemini :</span>
            <p>{{ coachingComp.ai_justification }}</p>
          </div>

          <div class="drawer-chat">
            <div class="chat-messages" ref="chatMessages">
              <div
                v-for="(msg, i) in chatHistory"
                :key="i"
                class="chat-msg"
                :class="msg.role"
              >
                <div class="msg-bubble">{{ msg.content }}</div>
              </div>
              <div v-if="isCoachLoading" class="chat-msg assistant">
                <div class="msg-bubble typing">
                  <span /><span /><span />
                </div>
              </div>
            </div>

            <!-- Chips de questions rapides — visibles seulement au démarrage -->
            <div v-if="chatHistory.length === 0 && !isCoachLoading" class="quick-chips">
              <button
                v-for="chip in quickChips"
                :key="chip"
                class="chip-btn"
                @click="sendQuickChip(chip)"
                :disabled="isCoachLoading"
              >{{ chip }}</button>
            </div>

            <div class="chat-input-row">
              <input
                v-model="coachInput"
                class="chat-input"
                placeholder="Posez votre question…"
                @keydown.enter.prevent="sendCoachMessage"
                :disabled="isCoachLoading"
                aria-label="Message au coach CV"
              />
              <button
                class="send-btn"
                @click="sendCoachMessage"
                :disabled="!coachInput.trim() || isCoachLoading"
                aria-label="Envoyer"
              >
                <Send :size="16" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import axios from 'axios'
import StarRating from './StarRating.vue'
import {
  Award, RefreshCw, Check, X, Info, MessageSquare, Send, BrainCircuit, Zap, Loader2
} from 'lucide-vue-next'

const props = defineProps<{
  userId: number
  readonly?: boolean
}>()

interface Evaluation {
  id: number
  competency_id: number
  competency_name: string
  ai_score: number | null
  ai_justification: string | null
  ai_scored_at: string | null
  user_score: number | null
  user_comment: string | null
}

// ── State ──────────────────────────────────────────────────────────────────
const evaluations = ref<Evaluation[]>([])
const isLoading = ref(false)
const isTriggering = ref(false)

// Feedback d'état par ligne (Set de competency_id)
const savingIds = ref<Set<number>>(new Set())
const savedIds = ref<Set<number>>(new Set())
// Debounce timers par ligne
const saveTimers = new Map<number, ReturnType<typeof setTimeout>>()
// Timers pour effacer le badge "sauvegardé"
const savedFadeTimers = new Map<number, ReturnType<typeof setTimeout>>()

const coachDrawerOpen = ref(false)
const coachingComp = ref<Evaluation | null>(null)
const coachInput = ref('')
const chatHistory = ref<{ role: 'user' | 'assistant'; content: string }[]>([])
const isCoachLoading = ref(false)
const chatMessages = ref<HTMLElement | null>(null)

// ── Fetch ──────────────────────────────────────────────────────────────────
async function fetchEvaluations() {
  isLoading.value = true
  try {
    const res = await axios.get(`/api/competencies/evaluations/user/${props.userId}`)
    evaluations.value = (res.data || []).sort((a: Evaluation, b: Evaluation) =>
      a.competency_name.localeCompare(b.competency_name)
    )
  } catch (e) {
    console.error('Failed to fetch evaluations', e)
  } finally {
    isLoading.value = false
  }
}

async function triggerAiScoring() {
  isTriggering.value = true
  try {
    await axios.post(`/api/competencies/evaluations/user/${props.userId}/ai-score-all`)
    setTimeout(fetchEvaluations, 3000)
    setTimeout(fetchEvaluations, 8000)
  } catch (e) {
    console.error('Failed to trigger AI scoring', e)
  } finally {
    setTimeout(() => { isTriggering.value = false }, 2000)
  }
}

// ── Évaluation utilisateur inline avec debounce ────────────────────────────
function onUserScoreChange(ev: Evaluation, newScore: number) {
  // Mise à jour optimiste immédiate
  const idx = evaluations.value.findIndex(e => e.competency_id === ev.competency_id)
  if (idx !== -1) {
    evaluations.value[idx] = { ...evaluations.value[idx], user_score: newScore }
  }

  // Annuler le timer précédent pour cette compétence (debounce)
  if (saveTimers.has(ev.competency_id)) {
    clearTimeout(saveTimers.get(ev.competency_id)!)
  }
  // Annuler le timer "saved fade" si toujours affiché
  if (savedFadeTimers.has(ev.competency_id)) {
    clearTimeout(savedFadeTimers.get(ev.competency_id)!)
    savedIds.value = new Set([...savedIds.value].filter(id => id !== ev.competency_id))
  }

  // Debounce 400ms : évite un appel API à chaque clic de survol
  const timer = setTimeout(async () => {
    savingIds.value = new Set([...savingIds.value, ev.competency_id])
    try {
      const res = await axios.post(
        `/api/competencies/evaluations/user/${props.userId}/competency/${ev.competency_id}/user-score`,
        { score: newScore, comment: null }
      )
      // Synchronise avec la réponse serveur
      const idx2 = evaluations.value.findIndex(e => e.competency_id === ev.competency_id)
      if (idx2 !== -1) {
        evaluations.value[idx2] = { ...evaluations.value[idx2], ...res.data }
      }
      // Afficher le checkmark "sauvegardé"
      savedIds.value = new Set([...savedIds.value, ev.competency_id])
      const fadeTimer = setTimeout(() => {
        savedIds.value = new Set([...savedIds.value].filter(id => id !== ev.competency_id))
      }, 1800)
      savedFadeTimers.set(ev.competency_id, fadeTimer)
    } catch (e) {
      console.error('Failed to save score', e)
    } finally {
      savingIds.value = new Set([...savingIds.value].filter(id => id !== ev.competency_id))
      saveTimers.delete(ev.competency_id)
    }
  }, 400)
  saveTimers.set(ev.competency_id, timer)
}

// ── Coach Drawer ───────────────────────────────────────────────────────────

// Questions rapides sugérées selon le contexte de la compétence
const quickChips = [
  'Comment améliorer mon CV sur cette compétence ?',
  'Comment la mettre en avant dans une proposition commerciale ?',
  'Quels projets concrets pourraient renforcer cette compétence ?',
  'Comment la formuler pour un recruteur ?',
]

function sendQuickChip(question: string) {
  coachInput.value = question
  sendCoachMessage()
}

function openCoach(ev: Evaluation) {
  coachingComp.value = ev
  coachDrawerOpen.value = true
  // Démarrage sans message d'accueil : les chips suffisent comme point d'entrée
  chatHistory.value = []
  coachInput.value = ''
}

async function sendCoachMessage() {
  const msg = coachInput.value.trim()
  if (!msg || isCoachLoading.value) return

  chatHistory.value.push({ role: 'user', content: msg })
  coachInput.value = ''
  isCoachLoading.value = true

  await nextTick()
  chatMessages.value?.scrollTo({ top: chatMessages.value.scrollHeight, behavior: 'smooth' })

  try {
    const context = [
      `Compétence : ${coachingComp.value?.competency_name}`,
      coachingComp.value?.ai_score !== null
        ? `Note Gemini : ${coachingComp.value?.ai_score}/5. Justification : ${coachingComp.value?.ai_justification}`
        : 'Pas encore de note Gemini.',
      coachingComp.value?.user_score !== null
        ? `Auto-évaluation : ${coachingComp.value?.user_score}/5`
        : 'Pas encore d\'auto-évaluation.',
    ].join('\n')

    const fullQuery = `[Contexte consultant]\n${context}\n\n[Question]\n${msg}`
    const res = await axios.post('/api/query', { query: fullQuery })
    const response = res.data?.response || res.data?.answer || 'Je n\'ai pas pu générer une réponse.'
    chatHistory.value.push({ role: 'assistant', content: response })
  } catch (e) {
    chatHistory.value.push({
      role: 'assistant',
      content: 'Désolé, une erreur s\'est produite. Veuillez réessayer.'
    })
  } finally {
    isCoachLoading.value = false
    await nextTick()
    chatMessages.value?.scrollTo({ top: chatMessages.value.scrollHeight, behavior: 'smooth' })
  }
}

onMounted(fetchEvaluations)
</script>

<style scoped>
.eval-panel {
  /* fond transparent : hérite du panel-card blanc du parent */
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
}

.eval-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.eval-title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.eval-title-row h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #111;
}

.eval-icon { color: #f59e0b; }

.eval-actions { display: flex; gap: 0.5rem; align-items: center; }

.eval-subtitle {
  font-size: 0.75rem;
  color: #6b7280;
  margin: 0 0 1rem;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.85rem;
  background: linear-gradient(135deg, #e31937, #c01228);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.15s;
}
.btn-primary:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-ghost {
  display: inline-flex;
  align-items: center;
  padding: 0.4rem;
  background: #f8f9fa;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  color: #6b7280;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-ghost:hover { background: #f0f0f0; color: #374151; }

/* Skeleton */
.eval-skeleton { display: flex; flex-direction: column; gap: 0.6rem; }
.skeleton-row {
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(90deg, #f3f4f6 25%, #e9eaec 50%, #f3f4f6 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* Empty */
.eval-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem;
  color: #9ca3af;
}

/* Table */
.eval-table-wrap { overflow-x: auto; }
.eval-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.eval-table th {
  text-align: left;
  padding: 0.4rem 0.75rem;
  color: #6b7280;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 2px solid #f3f4f6;
  white-space: nowrap;
}
.th-coach { width: 48px; text-align: center; }

.eval-row td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #f3f4f6;
  transition: background 0.15s;
}
.eval-row:hover td { background: #fafafa; }

/* Feedback par ligne */
.eval-row.saving td { background: #fffbeb; }
.eval-row.saved td { background: #f0fdf4; }

.comp-name {
  font-weight: 600;
  color: #1e293b;
  max-width: 200px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.score-cell { white-space: nowrap; }

/* Colonne utilisateur — affichage inline des étoiles + feedback */
.user-score-cell { min-width: 180px; }
.user-score-row {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.score-with-tip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.score-num {
  font-size: 0.75rem;
  color: #6b7280;
  font-variant-numeric: tabular-nums;
}

.score-num--user {
  min-width: 22px;
}

.score-pending { color: #9ca3af; font-size: 0.85rem; }

.tip-btn {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  transition: color 0.15s;
}
.tip-btn:hover { color: #f59e0b; }

/* Feedback icons */
.feedback-icon {
  display: inline-flex;
  align-items: center;
}
.saving-icon { color: #d97706; }
.saved-icon { color: #16a34a; }

.action-cell {
  text-align: center;
  white-space: nowrap;
}

/* Bouton Coach */
.coach-btn {
  background: #f8f9fa;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 0.3rem;
  cursor: pointer;
  color: #6b7280;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
}
.coach-btn:hover { border-color: #e31937; color: #e31937; background: rgba(227,25,55,0.06); }

/* Spin animations */
.spin { animation: spin 1s linear infinite; }
.spin-anim { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Coach Drawer */
.coach-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 1000;
  backdrop-filter: blur(4px);
  display: flex;
  justify-content: flex-end;
}

.coach-drawer {
  width: min(480px, 95vw);
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 1.5rem;
  background: rgba(15, 20, 35, 0.95);
  border-left: 1px solid rgba(255,255,255,0.1);
  animation: slideIn 0.25s ease;
}

@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.drawer-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.95rem;
  color: #f1f5f9;
}

.close-btn {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  transition: color 0.15s;
}
.close-btn:hover { color: #f1f5f9; }

.drawer-scores {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 0.75rem;
}

.dscore-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.dscore-label {
  font-size: 0.7rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.drawer-justification {
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 8px;
  padding: 0.75rem;
  margin-bottom: 1rem;
  font-size: 0.82rem;
  color: #cbd5e1;
}

.just-label {
  font-weight: 600;
  color: #f59e0b;
  font-size: 0.75rem;
  display: block;
  margin-bottom: 0.25rem;
}

.drawer-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-height: 0;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding-right: 4px;
}

.chat-msg { display: flex; }
.chat-msg.user { justify-content: flex-end; }
.chat-msg.assistant { justify-content: flex-start; }

.msg-bubble {
  max-width: 85%;
  padding: 0.6rem 0.9rem;
  border-radius: 12px;
  font-size: 0.85rem;
  line-height: 1.5;
  white-space: pre-wrap;
}

.chat-msg.user .msg-bubble {
  background: linear-gradient(135deg, #e31937, #c01228);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.chat-msg.assistant .msg-bubble {
  background: rgba(255,255,255,0.07);
  color: #e2e8f0;
  border-bottom-left-radius: 4px;
}

.typing { display: flex; align-items: center; gap: 4px; }
.typing span {
  width: 6px; height: 6px;
  background: #94a3b8;
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

.chat-input-row {
  display: flex;
  gap: 0.5rem;
}

.chat-input {
  flex: 1;
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 10px;
  padding: 0.55rem 0.85rem;
  color: #f1f5f9;
  font-size: 0.85rem;
  outline: none;
  transition: border-color 0.2s;
}
.chat-input:focus { border-color: #e31937; }
.chat-input::placeholder { color: #475569; }

.send-btn {
  background: #e31937;
  border: none;
  border-radius: 10px;
  padding: 0.55rem 0.75rem;
  color: #fff;
  cursor: pointer;
  transition: opacity 0.2s;
}
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.send-btn:hover:not(:disabled) { opacity: 0.85; }

/* Quick chips */
.quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.25rem 0 0.5rem;
}

.chip-btn {
  display: inline-flex;
  align-items: center;
  padding: 0.4rem 0.85rem;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 20px;
  color: #cbd5e1;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s;
  text-align: left;
  line-height: 1.3;
}
.chip-btn:hover:not(:disabled) {
  background: rgba(227, 25, 55, 0.12);
  border-color: rgba(227, 25, 55, 0.4);
  color: #fca5a5;
}
.chip-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
