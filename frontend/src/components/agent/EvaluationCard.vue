<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  evaluation: {
    competency_id?: number
    competency_name: string
    ai_score?: number | null
    user_score?: number | null
    ai_justification?: string
    scoring_version?: string
  }
}>()

const scoreColor = computed(() => {
  const s = props.evaluation.ai_score
  if (s === null || s === undefined) return '#94a3b8'
  if (s >= 4) return '#10b981'
  if (s >= 2.5) return '#f59e0b'
  return '#ef4444'
})

const scoreLabel = computed(() => {
  const s = props.evaluation.ai_score
  if (s === null || s === undefined) return 'N/A'
  return `${s}/5`
})
</script>

<template>
  <div class="evaluation-card" role="listitem">
    <div class="eval-header">
      <span class="eval-name">{{ evaluation.competency_name }}</span>
      <div class="eval-scores">
        <span class="score ai-score" :style="{ color: scoreColor, borderColor: scoreColor }">
          🤖 {{ scoreLabel }}
        </span>
        <span v-if="evaluation.user_score !== null && evaluation.user_score !== undefined"
              class="score user-score">
          👤 {{ evaluation.user_score }}/5
        </span>
      </div>
    </div>
    <p v-if="evaluation.ai_justification" class="eval-justification" :title="evaluation.ai_justification">
      {{ evaluation.ai_justification }}
    </p>
    <span v-if="evaluation.scoring_version" class="eval-version">{{ evaluation.scoring_version }}</span>
  </div>
</template>

<style scoped>
.evaluation-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.evaluation-card:hover {
  border-color: rgba(227, 25, 55, 0.2);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.eval-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.eval-name {
  font-size: 0.85rem;
  font-weight: 700;
  color: #1e293b;
  flex: 1;
}

.eval-scores {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.score {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.ai-score {
  background: rgba(0, 0, 0, 0.02);
}

.user-score {
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.25);
  background: rgba(99, 102, 241, 0.05);
}

.eval-justification {
  font-size: 0.76rem;
  color: #64748b;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  margin: 0;
}

.eval-version {
  font-size: 0.62rem;
  color: #94a3b8;
  font-family: monospace;
  align-self: flex-end;
}
</style>
