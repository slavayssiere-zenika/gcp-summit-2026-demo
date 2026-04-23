<template>
  <!-- Cache hit badge -->
  <div v-if="semanticCacheHit" class="cost-badge cost-badge--cache" title="Réponse servie depuis le cache sémantique — aucun appel LLM facturé">
    <Zap size="12" />
    <span>Semantic Cache</span>
    <span class="cost-divider">|</span>
    <span class="cost-value cost-value--cache">0 tokens</span>
    <span class="cost-divider">|</span>
    <span class="cost-value cost-value--cache">$0.000000</span>
  </div>
  <!-- Normal LLM badge -->
  <div v-else-if="usage" class="cost-badge" :class="{ 'cost-badge--hallucination': hasHallucinationWarning }" :title="hallucinationTitle">
    <AlertTriangle v-if="hasHallucinationWarning" size="12" class="hallucination-icon" aria-label="Risque d'hallucination détecté" />
    <Database v-else size="12" />
    <span>{{ totalTokens }} tokens</span>
    <span class="cost-divider">|</span>
    <span class="cost-value" :class="{ 'cost-value--hallucination': hasHallucinationWarning }">${{ costFormatted }}</span>
    <span v-if="hasHallucinationWarning" class="hallucination-label" :title="hallucinationDetail">
      ⚠ Hallucination
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Database, Zap, AlertTriangle } from 'lucide-vue-next'
import type { Usage } from '@/types'

const props = defineProps<{
  usage?: Usage
  semanticCacheHit?: boolean
  steps?: Array<{ type: string; tool?: string; args?: Record<string, unknown> }>
}>()

const totalTokens = computed(() => {
  if (!props.usage) return 0;
  return (props.usage.total_input_tokens || 0) + (props.usage.total_output_tokens || 0);
})

const costFormatted = computed(() => {
  if (!props.usage) return '0.000000';
  return (props.usage.estimated_cost_usd || 0).toFixed(6);
})

/** Guardrail warning steps from the agent response. */
const guardrailSteps = computed(() => {
  if (!props.steps) return [];
  return props.steps.filter(
    (s) =>
      s.type === 'warning' &&
      typeof s.tool === 'string' &&
      (s.tool === 'GUARDRAIL' ||
        s.tool === 'GUARDRAIL_ID_INVENTION' ||
        s.tool === 'GUARDRAIL_NAME_GROUNDING' ||
        s.tool === 'GUARDRAIL_COM006' ||
        s.tool.endsWith(':GUARDRAIL'))
  );
})

const hasHallucinationWarning = computed(() => guardrailSteps.value.length > 0)

const hallucinationTitle = computed(() => {
  if (!hasHallucinationWarning.value) return 'Coût estimé de cet appel à l\'IA';
  const types = [...new Set(guardrailSteps.value.map((s) => s.tool))].join(', ');
  return `⚠ Risque d'hallucination détecté (${types}). Vérifiez l'onglet Expert pour les détails.`;
})

const hallucinationDetail = computed(() => {
  return guardrailSteps.value
    .map((s) => (s.args as Record<string, unknown>)?.message as string)
    .filter(Boolean)
    .join(' | ');
})
</script>

<style scoped>
.cost-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 0.4rem 0.8rem;
  border-radius: var(--radius-md);
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  font-weight: 600;
  margin-left: auto;
  border-left: 3px solid #10b981;
  transition: border-color 0.2s, background 0.2s;
}

.cost-badge--cache {
  background: linear-gradient(135deg, #fdf4ff 0%, #f0fdf4 100%);
  border-color: #d8b4fe;
  border-left-color: #a855f7;
  color: #7e22ce;
  animation: cache-pulse 2s ease-in-out;
}

/* Hallucination warning state */
.cost-badge--hallucination {
  background: linear-gradient(135deg, #fff7ed 0%, #fef2f2 100%);
  border-color: #fca5a5;
  border-left-color: #ef4444;
  color: #991b1b;
  animation: hallucination-pulse 3s ease-in-out infinite;
}

.cost-value--cache {
  color: #a855f7;
}

.cost-value--hallucination {
  color: #dc2626;
}

.hallucination-icon {
  color: #ef4444;
  flex-shrink: 0;
}

.hallucination-label {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #dc2626;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  cursor: help;
  white-space: nowrap;
}

@keyframes cache-pulse {
  0% { opacity: 0.6; transform: scale(0.97); }
  50% { opacity: 1; transform: scale(1.01); }
  100% { opacity: 1; transform: scale(1); }
}

@keyframes hallucination-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
  50% { box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15); }
}

.cost-divider {
  opacity: 0.3;
}

.cost-value {
  color: #059669;
}
</style>
