<template>
  <div class="expert-mode">

    <!-- ═══ Section CoT (Raisonnement) ════════════════════════════ -->
    <div v-if="message.thoughts" class="expert-section">
      <button class="section-toggle" @click="thoughtsOpen = !thoughtsOpen" aria-label="Afficher le raisonnement IA">
        <div class="section-toggle-left">
          <span class="section-icon thought-icon">
            <BrainCircuit size="15" />
          </span>
          <span class="section-label">Raisonnement de l'IA <span class="section-sublabel">(Chain-of-Thought)</span></span>
        </div>
        <ChevronDown size="16" :class="['chevron', { open: thoughtsOpen }]" />
      </button>
      <Transition name="slide">
        <div v-if="thoughtsOpen" class="thought-body" v-html="md.render(message.thoughts)" />
      </Transition>
    </div>

    <!-- ═══ Section Pipeline MCP ═══════════════════════════════════ -->
    <div class="expert-section pipeline-section">
      <div class="pipeline-header">
        <span class="section-icon pipeline-icon"><Terminal size="15" /></span>
        <span class="section-label">Pipeline d'exécution MCP</span>
        <span class="step-count-badge">{{ (message.steps || []).length }} étape{{ (message.steps || []).length > 1 ? 's' : '' }}</span>
      </div>

      <div v-if="!message.steps || message.steps.length === 0" class="no-steps">
        <Info size="14" /> Aucun appel d'outil enregistré.
      </div>

      <div v-else class="steps-timeline">
        <div
          v-for="(step, idx) in message.steps"
          :key="idx"
          :class="['step-card', stepClass(step), { open: openSteps.has(idx) }]"
        >
          <!-- ── Step Header (toujours visible) ── -->
          <button class="step-header" @click="toggleStep(idx)" :aria-label="`Étape ${idx + 1}: ${step.tool || step.type}`">
            <div class="step-header-left">
              <span class="step-number">#{{ idx + 1 }}</span>
              <span :class="['step-type-badge', typeBadgeClass(step)]">
                <component :is="stepIcon(step)" size="11" />
                {{ stepTypeLabel(step) }}
              </span>
              <span class="step-tool-name">{{ step.tool || (step.data?.agent ? step.data.agent.replace('_', ' ') : 'result') }}</span>
              <!-- Param preview (inline, quand replié) -->
              <span v-if="!openSteps.has(idx) && inlinePreview(step)" class="step-param-preview">
                {{ inlinePreview(step) }}
              </span>
            </div>
            <div class="step-header-right">
              <span :class="['step-status-dot', step.type === 'error' ? 'error' : 'ok']" :title="step.type === 'error' ? 'Erreur' : 'Succès'"></span>
              <ChevronDown size="14" :class="['chevron', { open: openSteps.has(idx) }]" />
            </div>
          </button>

          <!-- ── Step Body (collapsible) ── -->
          <Transition name="slide">
            <div v-if="openSteps.has(idx)" class="step-body">
              <!-- Agent badge si A2A -->
              <div v-if="step.data?.agent" class="a2a-badge">
                <Bot size="12" />
                Délégation A2A → <strong>{{ step.data.agent.replace('_', ' ').toUpperCase() }}</strong>
              </div>

              <!-- Payload -->
              <div class="payload-block">
                <div class="payload-toolbar">
                  <span class="payload-label">
                    <Code2 size="12" /> {{ step.type === 'call' ? 'Paramètres' : 'Réponse' }}
                  </span>
                  <button class="copy-btn" @click.stop="copyPayload(step, idx)" :aria-label="`Copier le payload de l'étape ${idx + 1}`">
                    <template v-if="copiedIdx === idx">
                      <CheckCircle2 size="12" /> Copié !
                    </template>
                    <template v-else>
                      <Copy size="12" /> Copier
                    </template>
                  </button>
                </div>
                <pre class="payload-pre">{{ formatPayload(step) }}</pre>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </div>

    <!-- ═══ Section Réponse brute JSON ════════════════════════════ -->
    <div v-if="message.rawResponse" class="expert-section">
      <button class="section-toggle" @click="rawOpen = !rawOpen" aria-label="Voir la réponse brute JSON">
        <div class="section-toggle-left">
          <span class="section-icon raw-icon"><FileJson size="15" /></span>
          <span class="section-label">Réponse brute <span class="section-sublabel">(JSON)</span></span>
        </div>
        <ChevronDown size="16" :class="['chevron', { open: rawOpen }]" />
      </button>
      <Transition name="slide">
        <pre v-if="rawOpen" class="raw-json">{{ message.rawResponse }}</pre>
      </Transition>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import {
  Terminal, ChevronDown, Bot, Copy, CheckCircle2, Code2,
  FileJson, BrainCircuit, PlayCircle, Database, Info, Zap
} from 'lucide-vue-next'
import markdownit from 'markdown-it'
import type { Message, Step } from '@/types'

const md = markdownit()

const props = defineProps<{ message: Message }>()

// ── Accordion state ───────────────────────────────────────────
const thoughtsOpen = ref(false)
const rawOpen = ref(false)
const openSteps = reactive(new Set<number>())
const copiedIdx = ref<number | null>(null)

const toggleStep = (idx: number) => {
  if (openSteps.has(idx)) openSteps.delete(idx)
  else openSteps.add(idx)
}

// ── Step classification helpers ───────────────────────────────
const stepClass = (step: Step) => {
  if (step.type === 'call') return 'step-call'
  if (step.data?.agent) return 'step-a2a'
  if (step.type === 'error') return 'step-error'
  return 'step-result'
}

const typeBadgeClass = (step: Step) => {
  if (step.type === 'call') return 'badge-call'
  if (step.data?.agent) return 'badge-a2a'
  if (step.type === 'error') return 'badge-error'
  return 'badge-result'
}

const stepTypeLabel = (step: Step): string => {
  if (step.type === 'call') return 'CALL'
  if (step.data?.agent) return 'A2A'
  if (step.type === 'error') return 'ERREUR'
  return 'RESULT'
}

const stepIcon = (step: Step) => {
  if (step.type === 'call') return PlayCircle
  if (step.data?.agent) return Bot
  if (step.type === 'error') return Zap
  return Database
}

// ── Inline preview (1–2 key params, visible quand replié) ────
const inlinePreview = (step: Step): string => {
  const payload = step.args || step.data
  if (!payload || typeof payload !== 'object') return ''
  const keys = Object.keys(payload).filter(k => k !== 'agent' && k !== 'session_id')
  if (keys.length === 0) return ''
  const preview = keys.slice(0, 2).map(k => {
    const val = payload[k]
    const strVal = typeof val === 'string' ? val : JSON.stringify(val)
    return `${k}: ${strVal.length > 30 ? strVal.slice(0, 30) + '…' : strVal}`
  }).join('  ·  ')
  return `{ ${preview} }`
}

// ── Payload format ────────────────────────────────────────────
const formatPayload = (step: Step): string => {
  const payload = step.args || step.data
  if (!payload) return '(vide)'
  try { return JSON.stringify(payload, null, 2) } catch { return String(payload) }
}

// ── Copy to clipboard ─────────────────────────────────────────
const copyPayload = async (step: Step, idx: number) => {
  try {
    await navigator.clipboard.writeText(formatPayload(step))
    copiedIdx.value = idx
    setTimeout(() => { copiedIdx.value = null }, 2000)
  } catch { /* ignore */ }
}
</script>

<style scoped>
/* ═══ Animations ════════════════════════════════════════════ */
.expert-mode {
  display: flex;
  flex-direction: column;
  gap: 10px;
  animation: fadeIn 0.25s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.slide-enter-from,
.slide-leave-to {
  max-height: 0;
  opacity: 0;
}
.slide-enter-to,
.slide-leave-from {
  max-height: 2000px;
  opacity: 1;
}

/* ═══ Sections ══════════════════════════════════════════════ */
.expert-section {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
}

.section-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 0.15s;
  gap: 8px;
}

.section-toggle:hover { background: #f1f5f9; }

.section-toggle-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-label {
  font-size: 0.78rem;
  font-weight: 700;
  color: #334155;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.section-sublabel {
  font-weight: 400;
  text-transform: none;
  color: #94a3b8;
  font-size: 0.72rem;
  letter-spacing: 0;
  margin-left: 2px;
}

/* ═══ Chevron ═══════════════════════════════════════════════ */
.chevron {
  color: #94a3b8;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}
.chevron.open {
  transform: rotate(180deg);
}

/* ═══ Section Icons ═════════════════════════════════════════ */
.section-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  flex-shrink: 0;
}
.thought-icon  { background: #ede9fe; color: #7c3aed; }
.pipeline-icon { background: #fff1f2; color: #e31937; }
.raw-icon      { background: #f0fdf4; color: #16a34a; }

/* ═══ Pipeline Section ══════════════════════════════════════ */
.pipeline-section { border-color: rgba(227, 25, 55, 0.15); }

.pipeline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px 8px;
  border-bottom: 1px solid #e2e8f0;
}

.step-count-badge {
  margin-left: auto;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #64748b;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 20px;
  letter-spacing: 0.03em;
}

.no-steps {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 14px 16px;
  font-size: 0.82rem;
  color: #94a3b8;
  font-style: italic;
}

/* ═══ Steps Timeline ════════════════════════════════════════ */
.steps-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.step-card {
  border-top: 1px solid #f1f5f9;
  transition: background 0.15s;
}
.step-card:first-child { border-top: none; }
.step-card.open { background: white; }

/* Colored left border per type */
.step-call   { border-left: 3px solid #e31937; }
.step-result { border-left: 3px solid #10b981; }
.step-a2a    { border-left: 3px solid #0ea5e9; }
.step-error  { border-left: 3px solid #f59e0b; }

/* ── Step header (clickable row) ── */
.step-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  gap: 8px;
  transition: background 0.15s;
}
.step-header:hover { background: #f8fafc; }

.step-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.step-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.step-number {
  font-size: 0.65rem;
  font-weight: 800;
  color: #94a3b8;
  font-family: 'JetBrains Mono', monospace;
  min-width: 22px;
}

/* Type badges */
.step-type-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  padding: 2px 7px;
  border-radius: 4px;
  flex-shrink: 0;
}
.badge-call   { background: #fff1f2; color: #e31937; border: 1px solid rgba(227,25,55,0.2); }
.badge-result { background: #f0fdf4; color: #16a34a; border: 1px solid rgba(22,163,74,0.2); }
.badge-a2a    { background: #e0f2fe; color: #0284c7; border: 1px solid rgba(2,132,199,0.2); }
.badge-error  { background: #fffbeb; color: #d97706; border: 1px solid rgba(217,119,6,0.2); }

.step-tool-name {
  font-size: 0.8rem;
  font-weight: 700;
  color: #1e293b;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.step-param-preview {
  font-size: 0.72rem;
  color: #94a3b8;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

/* Status dot */
.step-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.step-status-dot.ok    { background: #10b981; box-shadow: 0 0 0 2px rgba(16,185,129,0.2); }
.step-status-dot.error { background: #f59e0b; box-shadow: 0 0 0 2px rgba(245,158,11,0.2); }

/* ── Step Body (content) ── */
.step-body {
  padding: 10px 14px 12px 14px;
  border-top: 1px solid #f1f5f9;
}

.a2a-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.7rem;
  font-weight: 700;
  background: #e0f2fe;
  color: #0284c7;
  padding: 3px 10px;
  border-radius: 20px;
  margin-bottom: 8px;
  letter-spacing: 0.03em;
}

/* ── Payload block ── */
.payload-block {
  background: #1e293b;
  border-radius: 8px;
  overflow: hidden;
}

.payload-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: #0f172a;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.payload-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.68rem;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.copy-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  color: #64748b;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.copy-btn:hover { background: rgba(255,255,255,0.1); color: #cbd5e1; }

.payload-pre {
  padding: 10px 12px;
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.6;
  color: #e2e8f0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 320px;
  overflow-y: auto;
}

/* ── Scrollbar dark theme ── */
.payload-pre::-webkit-scrollbar { width: 4px; }
.payload-pre::-webkit-scrollbar-track { background: transparent; }
.payload-pre::-webkit-scrollbar-thumb { background: #334155; border-radius: 2px; }

/* ═══ CoT Thought body ══════════════════════════════════════ */
.thought-body {
  padding: 12px 16px;
  font-size: 0.875rem;
  color: #4c1d95;
  line-height: 1.7;
  background: #faf5ff;
  border-top: 1px solid #ede9fe;
}
.thought-body :deep(p) { margin: 0 0 0.5em; }
.thought-body :deep(p:last-child) { margin: 0; }

/* ═══ Raw JSON ══════════════════════════════════════════════ */
.raw-json {
  padding: 12px 16px;
  margin: 0;
  background: #1e293b;
  color: #94a3b8;
  font-size: 0.78rem;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  border-top: 1px solid #e2e8f0;
  max-height: 300px;
  overflow-y: auto;
}
</style>
