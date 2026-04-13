<template>
  <div class="tab-pane expert-mode">
    <!-- Chain of Thought (Thoughts) -->
    <div v-if="message.thoughts" class="thought-section">
      <div class="expert-header">
        <RefreshCw size="18" class="spin" style="color: #6366f1;" /> <span>Raisonnement de l'IA (CoT)</span>
      </div>
      <div class="thought-bubble" v-html="md.render(message.thoughts)">
      </div>
    </div>

    <div class="expert-header" :style="{ marginTop: message.thoughts ? '2rem' : '0' }">
      <Terminal size="18" /> <span>Exécution des microservices (MCP)</span>
    </div>
    
    <div class="steps-timeline">
      <div v-for="(step, idx) in message.steps" :key="idx" :class="['step-item', step.type]">
        <div class="step-icon">
          <PlayCircle v-if="step.type === 'call'" size="14" />
          <Database v-else size="14" />
        </div>
        <div class="step-details">
          <div class="step-title">
            <strong v-if="step.type === 'call'">APPEL OUTIL: {{ step.tool }}</strong>
            <strong v-else>RÉSULTAT BRUT</strong>
          </div>
          <pre class="step-payload">{{ JSON.stringify(step.args || step.data, null, 2) }}</pre>
        </div>
      </div>
      <div v-if="!message.steps || message.steps.length === 0" class="no-steps">
        Aucun appel d'outil n'a été enregistré pour cette réponse.
      </div>
    </div>

    <div v-if="message.rawResponse" class="expert-header" style="margin-top: 2rem;">
      <FileCode size="18" /> <span>Réponse brute de l'IA (JSON)</span>
    </div>
    <pre v-if="message.rawResponse" class="json-viewer">{{ message.rawResponse }}</pre>
  </div>
</template>

<script setup lang="ts">
import { RefreshCw, Terminal, PlayCircle, Database, FileCode } from 'lucide-vue-next'
import markdownit from 'markdown-it'
import type { Message } from '@/types'

const md = markdownit()

defineProps<{
  message: Message
}>()
</script>

<style scoped>
.expert-mode {
  animation: fadeIn 0.3s ease-out;
}

.expert-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 1rem;
  color: var(--color-text-secondary);
  font-weight: 700;
  font-size: 0.9rem;
}

.steps-timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.step-item {
  display: flex;
  gap: 12px;
  padding: 1rem;
  background: var(--background-alt);
  border-radius: var(--radius-lg);
  border: var(--border-subtle);
}

.step-item.call {
  border-left: 4px solid var(--zenika-red);
}

.step-item.result {
  border-left: 4px solid #10b981;
}

.step-icon {
  margin-top: 2px;
  color: var(--color-text-secondary);
}

.step-details {
  flex: 1;
  overflow: hidden;
}

.step-title {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.step-payload {
  white-space: pre-wrap;
  word-break: break-all;
  background: #fff;
  padding: 0.75rem;
  border-radius: var(--radius-md);
  font-family: inherit;
  font-size: 0.85rem;
  border: 1px solid #f1f5f9;
}

.thought-section {
  margin-bottom: 1.5rem;
}

.thought-bubble {
  background: #f0f4ff;
  border-left: 4px solid #6366f1;
  padding: 1rem;
  border-radius: 0 12px 12px 0;
  font-size: 0.9rem;
  color: #312e81;
  font-style: italic;
  white-space: pre-wrap;
}

.json-viewer {
  background: #1e293b;
  color: #e2e8f0;
  padding: 1rem;
  border-radius: var(--radius-md);
  font-size: 0.85rem;
  overflow-x: auto;
}

.spin {
  animation: spin-anim 2s linear infinite;
}

@keyframes spin-anim {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
