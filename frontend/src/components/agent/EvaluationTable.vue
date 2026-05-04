<script setup lang="ts">
import { computed } from 'vue'
import EvaluationCard from './EvaluationCard.vue'

const props = defineProps<{
  evaluations: Array<{
    competency_id?: number
    competency_name: string
    ai_score?: number | null
    user_score?: number | null
    ai_justification?: string
    scoring_version?: string
    user_id?: number
  }>
}>()

// Sort by ai_score descending (null last)
const sorted = computed(() =>
  [...props.evaluations].sort((a, b) => {
    if (a.ai_score == null && b.ai_score == null) return 0
    if (a.ai_score == null) return 1
    if (b.ai_score == null) return -1
    return b.ai_score - a.ai_score
  })
)
</script>

<template>
  <div class="evaluation-table" role="list" aria-label="Évaluations de compétences">
    <div v-if="sorted.length === 0" class="eval-empty">
      Aucune évaluation disponible.
    </div>
    <EvaluationCard
      v-for="(ev, idx) in sorted"
      :key="ev.competency_id ?? idx"
      :evaluation="ev"
    />
  </div>
</template>

<style scoped>
.evaluation-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.eval-empty {
  font-size: 0.85rem;
  color: #94a3b8;
  text-align: center;
  padding: 1.5rem;
  background: #f8fafc;
  border-radius: 12px;
  border: 1px dashed #e2e8f0;
}
</style>
