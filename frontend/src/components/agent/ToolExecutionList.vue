<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle2, Cpu, XCircle } from 'lucide-vue-next'

const props = defineProps<{
  steps: {
    name?: string
    tool?: string
    type?: string
  }[]
}>()

// Ne conserver que les steps qui ont un nom d'outil valide (non vide).
// Cela filtre les events de type "result" qui n'ont pas de tool/name.
const namedSteps = computed(() =>
  props.steps.filter(s => !!(s.tool || s.name))
)

// Dédupliquer les outils consécutifs identiques et compter les occurrences
const deduped = computed(() => {
  const map = new Map<string, { tool: string; count: number; hasError: boolean }>()
  for (const step of namedSteps.value) {
    const key = step.tool || step.name || ''
    if (map.has(key)) {
      const entry = map.get(key)!
      entry.count++
      if (step.type === 'error') entry.hasError = true
    } else {
      map.set(key, { tool: key, count: 1, hasError: step.type === 'error' })
    }
  }
  return Array.from(map.values())
})
</script>

<template>
  <div v-if="namedSteps.length > 0" class="tool-execution-list">
    <div class="list-header">
      <Cpu size="13" />
      <span>Outils exécutés par l'agent</span>
      <span class="total-badge">{{ namedSteps.length }}</span>
    </div>
    <div class="steps-grid">
      <div v-for="(item, idx) in deduped" :key="idx" class="step-chip" :class="{ error: item.hasError }">
        <CheckCircle2 size="12" class="success-icon" v-if="!item.hasError" />
        <XCircle size="12" class="error-icon" v-else />
        <span class="step-name">{{ item.tool }}</span>
        <span v-if="item.count > 1" class="count-badge">×{{ item.count }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-execution-list {
  background: rgba(248, 250, 252, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  padding: 0.6rem 0.75rem;
  margin-top: 0.75rem;
}

.list-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.68rem;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.5rem;
}

.total-badge {
  margin-left: 2px;
  background: #e2e8f0;
  color: #64748b;
  font-size: 0.65rem;
  font-weight: 800;
  padding: 1px 5px;
  border-radius: 99px;
}

.steps-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.step-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: white;
  border: 1px solid #e2e8f0;
  padding: 3px 8px;
  border-radius: 6px;
  transition: border-color 0.15s;
}

.step-chip:hover {
  border-color: var(--zenika-red);
}

.step-chip.error {
  border-color: #fca5a5;
  background: #fff5f5;
}

.success-icon {
  color: #10b981;
  flex-shrink: 0;
}

.error-icon {
  color: #ef4444;
  flex-shrink: 0;
}

.step-name {
  font-size: 0.75rem;
  font-weight: 600;
  color: #334155;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  white-space: nowrap;
}

.count-badge {
  font-size: 0.65rem;
  font-weight: 700;
  color: #94a3b8;
  background: #f1f5f9;
  padding: 0 4px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
}
</style>
