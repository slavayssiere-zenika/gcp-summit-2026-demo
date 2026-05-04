<script setup lang="ts">
defineProps<{
  competency: {
    id?: number
    name: string
    description?: string
    aliases?: string | string[]
    parent_id?: number
  }
}>()
</script>

<template>
  <div class="competency-badge" role="listitem">
    <span class="comp-name">{{ competency.name }}</span>
    <span v-if="competency.description" class="comp-desc">{{ competency.description }}</span>
    <span v-if="competency.aliases" class="comp-alias">
      {{ Array.isArray(competency.aliases) ? competency.aliases.join(', ') : competency.aliases }}
    </span>
  </div>
</template>

<style scoped>
.competency-badge {
  background: rgba(227, 25, 55, 0.04);
  border: 1px solid rgba(227, 25, 55, 0.15);
  border-radius: 12px;
  padding: 0.6rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: border-color 0.15s;
}

.competency-badge:hover {
  border-color: rgba(227, 25, 55, 0.35);
}

.comp-name {
  font-size: 0.85rem;
  font-weight: 700;
  color: #1e293b;
}

.comp-desc {
  font-size: 0.75rem;
  color: #64748b;
  line-height: 1.4;
}

.comp-alias {
  font-size: 0.68rem;
  color: var(--zenika-red);
  font-style: italic;
}
</style>
