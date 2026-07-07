<script setup lang="ts">
import { authService } from '../services/auth'
import ConsultantDashboard from '@/components/ConsultantDashboard.vue'

const user = authService.state.user
</script>

<template>
  <div class="profile-page fade-in">
    <ConsultantDashboard v-if="user" :userId="user.id" :readonly="false" />
  </div>
</template>

<style scoped>
.profile-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 1.5rem 4rem;
}

.fade-in { animation: fadeIn 0.4s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
</style>
