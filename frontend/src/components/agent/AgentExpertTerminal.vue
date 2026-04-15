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
      <div v-for="(step, idx) in message.steps" :key="idx" :class="['step-item', step.type, step.data?.agent ? 'a2a-delegation' : '']">
        <div class="step-icon">
          <PlayCircle v-if="step.type === 'call'" size="14" />
          <Bot v-else-if="step.data?.agent" size="14" />
          <Database v-else size="14" />
        </div>
        <div class="step-details">
          <div class="step-title">
            <strong v-if="step.type === 'call'" class="agent-badge orchestrator">
              <Bot size="12" style="margin-right:4px; margin-bottom:-2px;" /> ORCHESTRATEUR
              <span style="color:#64748b; margin-left: 8px;">APPEL OUTIL: {{ step.tool }}</span>
            </strong>
            <strong v-else-if="step.data?.agent" class="agent-badge" :class="step.data.agent">
               <Bot size="12" style="margin-right:4px; margin-bottom:-2px;" /> {{ step.data.agent.replace('_', ' ').toUpperCase() }}
               <span style="color:#64748b; margin-left: 8px;">RÉPONSE A2A</span>
            </strong>
            <strong v-else>RÉSULTAT BRUT</strong>
          </div>
          <pre class="step-payload" :class="{'a2a-payload': step.data?.agent}">{{ JSON.stringify(step.args || step.data, null, 2) }}</pre>
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
import { RefreshCw, Terminal, PlayCircle, Database, FileCode, Bot } from 'lucide-vue-next'
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

.agent-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.6rem;
  border-radius: 6px;
  font-size: 0.70rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  box-shadow: 0 2px 5px rgba(0,0,0,0.05);
}

.agent-badge.orchestrator {
  background-color: #f8fafc;
  color: var(--zenika-red);
  border: 1px solid rgba(227, 25, 55, 0.2);
}

.agent-badge.hr_agent {
  background-color: #e0f2fe;
  color: #0284c7;
  border: 1px solid rgba(2, 132, 199, 0.2);
}

.agent-badge.ops_agent {
  background-color: #ede9fe;
  color: #7c3aed;
  border: 1px solid rgba(124, 58, 237, 0.2);
}

.step-item.a2a-delegation {
  border-left: 4px solid #0ea5e9;
  background: #f8fafc;
}

.step-payload.a2a-payload {
  background: #ffffff;
  border-color: #e0f2fe;
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
