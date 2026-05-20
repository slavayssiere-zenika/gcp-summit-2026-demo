<script setup lang="ts">
/**
 * HitlApproval.vue — Composant Human-in-the-Loop (Phase 3 ADK v2)
 *
 * Affiché dans le chat quand l'agent Missions retourne requires_human_approval=True.
 * L'utilisateur peut Approuver ou Rejeter le staffing proposé.
 * La décision est envoyée via POST /hitl/respond sur agent_missions_api.
 *
 * Usage dans AgentExpertTerminal.vue :
 *   <HitlApproval v-if="msg.hitlRequest" :request="msg.hitlRequest" @resolved="onHitlResolved" />
 */
import { ref } from 'vue'
import { CheckCircle, XCircle, Clock, AlertTriangle, User, Star, ChevronDown, ChevronUp } from 'lucide-vue-next'
import type { HitlRequest } from '@/types'
import { agentApi } from '@/services/agentApi'

const props = defineProps<{
  request: HitlRequest
}>()

const emit = defineEmits<{
  (e: 'resolved', payload: { hitl_id: string; decision: 'approved' | 'rejected'; comment: string }): void
}>()

const state = ref<'pending' | 'loading' | 'approved' | 'rejected'>('pending')
const comment = ref('')
const errorMsg = ref('')
const showCandidates = ref(false)

const expiresAt = new Date(props.request.expires_at)
const isExpired = Date.now() > expiresAt.getTime()

async function respond(decision: 'approved' | 'rejected') {
  if (state.value === 'loading' || isExpired) return
  state.value = 'loading'
  errorMsg.value = ''
  try {
    await agentApi.hitlRespond(props.request.hitl_id, decision, comment.value)
    state.value = decision
    emit('resolved', { hitl_id: props.request.hitl_id, decision, comment: comment.value })
  } catch (err: any) {
    errorMsg.value = err?.message || 'Erreur réseau lors de la validation'
    state.value = 'pending'
  }
}

function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`
}

function scoreClass(score: number): string {
  if (score >= 0.8) return 'score-high'
  if (score >= 0.6) return 'score-medium'
  return 'score-low'
}
</script>

<template>
  <div class="hitl-card" :class="{ 'hitl-resolved': state !== 'pending', 'hitl-expired': isExpired }">
    <!-- ── Header ─────────────────────────────────────────────────── -->
    <div class="hitl-header">
      <div class="hitl-icon">
        <AlertTriangle v-if="state === 'pending' && !isExpired" size="20" />
        <CheckCircle v-else-if="state === 'approved'" size="20" />
        <XCircle v-else-if="state === 'rejected'" size="20" />
        <Clock v-else size="20" />
      </div>
      <div class="hitl-title">
        <span class="hitl-badge" :class="`badge-${state === 'pending' && !isExpired ? 'warn' : state}`">
          {{ isExpired ? 'Expiré' : state === 'pending' ? 'Validation requise' : state === 'approved' ? 'Approuvé' : 'Rejeté' }}
        </span>
        <h4>{{ request.mission_title }}</h4>
      </div>
    </div>

    <!-- ── Raison ──────────────────────────────────────────────────── -->
    <p class="hitl-reason">{{ request.reason }}</p>

    <!-- ── Candidats (toggle) ──────────────────────────────────────── -->
    <button class="toggle-candidates" @click="showCandidates = !showCandidates">
      <User size="14" />
      {{ request.candidates.length }} consultant{{ request.candidates.length > 1 ? 's' : '' }} proposé{{ request.candidates.length > 1 ? 's' : '' }}
      <component :is="showCandidates ? ChevronUp : ChevronDown" size="14" />
    </button>

    <Transition name="slide-fade">
      <ul v-if="showCandidates" class="candidates-list">
        <li v-for="c in request.candidates" :key="c.consultant_id" class="candidate-item">
          <div class="candidate-name">
            <User size="13" />
            {{ c.full_name }}
          </div>
          <div class="candidate-score" :class="scoreClass(c.confidence_score)">
            <Star size="12" />
            {{ formatScore(c.confidence_score) }}
          </div>
        </li>
      </ul>
    </Transition>

    <!-- ── Commentaire ─────────────────────────────────────────────── -->
    <div v-if="state === 'pending' && !isExpired" class="hitl-comment">
      <textarea
        v-model="comment"
        placeholder="Commentaire optionnel (ex: raison du rejet, ajustement suggéré…)"
        rows="2"
        :disabled="state !== 'pending'"
      />
    </div>

    <!-- ── Erreur ──────────────────────────────────────────────────── -->
    <p v-if="errorMsg" class="hitl-error">⚠️ {{ errorMsg }}</p>

    <!-- ── Actions ────────────────────────────────────────────────── -->
    <div v-if="state === 'pending' && !isExpired" class="hitl-actions">
      <button
        class="btn btn-reject"
        :disabled="state === 'loading'"
        @click="respond('rejected')"
      >
        <XCircle size="15" />
        Rejeter
      </button>
      <button
        class="btn btn-approve"
        :disabled="state === 'loading'"
        @click="respond('approved')"
      >
        <template v-if="state === 'loading'">
          <span class="spinner" />
          En cours…
        </template>
        <template v-else>
          <CheckCircle size="15" />
          Approuver le staffing
        </template>
      </button>
    </div>

    <!-- ── Confirmation ───────────────────────────────────────────── -->
    <div v-else-if="state !== 'pending'" class="hitl-confirmed">
      <CheckCircle v-if="state === 'approved'" size="16" />
      <XCircle v-else-if="state === 'rejected'" size="16" />
      <span>Décision enregistrée — {{ state === 'approved' ? 'staffing validé' : 'staffing rejeté' }}</span>
    </div>
  </div>
</template>

<style scoped>
.hitl-card {
  background: rgba(251, 191, 36, 0.06);
  border: 1.5px solid rgba(251, 191, 36, 0.35);
  border-radius: 14px;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  font-size: 0.875rem;
  transition: all 0.3s ease;
  max-width: 520px;
}

.hitl-card.hitl-resolved {
  background: rgba(16, 185, 129, 0.05);
  border-color: rgba(16, 185, 129, 0.3);
}

.hitl-card.hitl-expired {
  background: rgba(148, 163, 184, 0.05);
  border-color: rgba(148, 163, 184, 0.25);
  opacity: 0.7;
}

/* Header */
.hitl-header {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.hitl-icon {
  color: #f59e0b;
  margin-top: 2px;
  flex-shrink: 0;
}
.hitl-resolved .hitl-icon { color: #10b981; }
.hitl-expired .hitl-icon { color: #94a3b8; }

.hitl-title {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.hitl-title h4 {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.3;
}

/* Badge */
.hitl-badge {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.15rem 0.5rem;
  border-radius: 6px;
}
.badge-warn { background: #fef3c7; color: #92400e; }
.badge-approved { background: #d1fae5; color: #065f46; }
.badge-rejected { background: #fee2e2; color: #991b1b; }
.badge-loading { background: #dbeafe; color: #1d4ed8; }

/* Reason */
.hitl-reason {
  margin: 0;
  color: #475569;
  line-height: 1.5;
  font-style: italic;
  border-left: 3px solid #fbbf24;
  padding-left: 0.75rem;
}

/* Toggle candidats */
.toggle-candidates {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 8px;
  padding: 0.35rem 0.75rem;
  font-size: 0.78rem;
  color: #64748b;
  cursor: pointer;
  width: fit-content;
  transition: all 0.2s;
  font-weight: 500;
}
.toggle-candidates:hover {
  background: rgba(0,0,0,0.04);
  color: #334155;
}

/* Candidates */
.candidates-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.candidate-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  backdrop-filter: blur(4px);
}

.candidate-name {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #334155;
  font-weight: 500;
}

.candidate-score {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.78rem;
  font-weight: 700;
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
}
.score-high { background: #d1fae5; color: #065f46; }
.score-medium { background: #fef3c7; color: #92400e; }
.score-low { background: #fee2e2; color: #991b1b; }

/* Textarea */
.hitl-comment textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid rgba(0,0,0,0.12);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  font-size: 0.82rem;
  color: #334155;
  background: rgba(255,255,255,0.8);
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.2s;
  outline: none;
}
.hitl-comment textarea:focus {
  border-color: #f59e0b;
  box-shadow: 0 0 0 3px rgba(251,191,36,0.12);
}

/* Error */
.hitl-error {
  margin: 0;
  color: #dc2626;
  font-size: 0.8rem;
}

/* Actions */
.hitl-actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  border: none;
  border-radius: 9px;
  padding: 0.5rem 1rem;
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  letter-spacing: 0.01em;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-approve {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(16,185,129,0.3);
}
.btn-approve:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(16,185,129,0.4);
}

.btn-reject {
  background: rgba(239,68,68,0.08);
  color: #dc2626;
  border: 1px solid rgba(239,68,68,0.2);
}
.btn-reject:not(:disabled):hover {
  background: rgba(239,68,68,0.14);
  border-color: rgba(239,68,68,0.35);
}

/* Confirmed */
.hitl-confirmed {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #10b981;
  font-weight: 600;
  font-size: 0.85rem;
}

/* Spinner */
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Transition */
.slide-fade-enter-active { transition: all 0.25s ease-out; }
.slide-fade-leave-active { transition: all 0.2s ease-in; }
.slide-fade-enter-from,
.slide-fade-leave-to { opacity: 0; transform: translateY(-6px); }
</style>
