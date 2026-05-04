<script setup lang="ts">
import CompetencyBadge from './CompetencyBadge.vue'

defineProps<{
  competencies: Array<{
    id?: number
    name: string
    description?: string
    aliases?: string | string[]
    parent_id?: number
  }>
}>()
</script>

<template>
  <div class="competency-list" role="list" aria-label="Liste des compétences">
    <CompetencyBadge
      v-for="(comp, idx) in competencies"
      :key="comp.id ?? idx"
      :competency="comp"
    />
  </div>
</template>

<style scoped>
.competency-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
