<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import ConsultantDashboard from '@/components/ConsultantDashboard.vue'

const route = useRoute()
const userId = ref(route.params.id as string)

watch(() => route.params.id, (newId) => {
  if (newId) userId.value = newId as string
})
</script>

<template>
  <div class="user-detail-page">
    <ConsultantDashboard :userId="userId" :readonly="true" />
  </div>
</template>

<style scoped>
.user-detail-page {
  padding: 2rem 1rem;
}
</style>
