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
  <div v-else-if="usage" class="cost-badge" title="Coût estimé de cet appel à l'IA">
    <Database size="12" />
    <span>{{ totalTokens }} tokens</span>
    <span class="cost-divider">|</span>
    <span class="cost-value">${{ costFormatted }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Database, Zap } from 'lucide-vue-next'
import type { Usage } from '@/types'

const props = defineProps<{
  usage?: Usage
  semanticCacheHit?: boolean
}>()

const totalTokens = computed(() => {
  if (!props.usage) return 0;
  return (props.usage.total_input_tokens || 0) + (props.usage.total_output_tokens || 0);
})

const costFormatted = computed(() => {
  if (!props.usage) return '0.000000';
  return (props.usage.estimated_cost_usd || 0).toFixed(6);
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
}

.cost-badge--cache {
  background: linear-gradient(135deg, #fdf4ff 0%, #f0fdf4 100%);
  border-color: #d8b4fe;
  border-left-color: #a855f7;
  color: #7e22ce;
  animation: cache-pulse 2s ease-in-out;
}

.cost-value--cache {
  color: #a855f7;
}

@keyframes cache-pulse {
  0% { opacity: 0.6; transform: scale(0.97); }
  50% { opacity: 1; transform: scale(1.01); }
  100% { opacity: 1; transform: scale(1); }
}

.cost-divider {
  opacity: 0.3;
}

.cost-value {
  color: #059669;
}
</style>
