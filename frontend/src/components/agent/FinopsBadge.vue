<template>
  <div v-if="usage" class="cost-badge" title="Coût estimé de cet appel à l'IA">
    <Database size="12" />
    <span>{{ totalTokens }} tokens</span>
    <span class="cost-divider">|</span>
    <span class="cost-value">${{ costFormatted }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Database } from 'lucide-vue-next'
import type { Usage } from '@/types'

const props = defineProps<{
  usage?: Usage
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

.cost-divider {
  opacity: 0.3;
}

.cost-value {
  color: #059669;
}
</style>
