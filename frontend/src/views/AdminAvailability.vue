<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { Calendar, CalendarDays } from 'lucide-vue-next'
import PageHeader from '../components/ui/PageHeader.vue'

const users = ref<any[]>([])
const isLoading = ref(true)

const fetchUsers = async () => {
    try {
        const token = localStorage.getItem('access_token')
        const response = await axios.get('/api/users/?limit=100', {
            headers: token ? { Authorization: `Bearer ${token}` } : {}
        })
        users.value = response.data.items.filter((u: any) => u.unavailability_periods && u.unavailability_periods.length > 0)
    } catch(err) {
        console.error(err)
    } finally {
        isLoading.value = false
    }
}

onMounted(() => {
    fetchUsers()
})
</script>
<template>
  <div class="admin-availability fade-in">

    <PageHeader
      title="Planning des Disponibilités"
      subtitle="Aperçu RH des congés, arrêts et staffings chez les clients pour optimiser les affectations de missions."
      :icon="CalendarDays"
      :breadcrumb="[
        { label: 'Hub RH' },
        { label: 'Planning Disponibilités' }
      ]"
    />

    <div v-if="isLoading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>Chargement des agendas...</span>
    </div>

    <div class="card" v-else>
      <table class="data-table">
        <thead>
          <tr><th>Consultant</th><th>Email</th><th>Indisponibilités</th></tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td class="font-bold">{{ user.full_name || user.username }}</td>
            <td>{{ user.email }}</td>
            <td>
              <div v-for="(p, i) in user.unavailability_periods" :key="i" class="period-badge">
                <strong>{{ p.start_date }}</strong> au <strong>{{ p.end_date }}</strong>
                <span class="type-tag">{{ p.type }}</span>
                <span class="reason-tag">[{{ p.reason }}]</span>
              </div>
            </td>
          </tr>
          <tr v-if="users.length === 0">
            <td colspan="3" class="empty">Aucun événement d'agenda déclaré pour l'instant.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<style scoped>
.admin-availability { padding: 2rem; max-width: 1200px; margin: 0 auto; }
.fade-in { animation: fadeIn 0.35s ease forwards; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.loading-state {
  display: flex; align-items: center; gap: 12px;
  padding: 2rem; color: #64748b; font-size: 0.95rem;
}
.loading-spinner {
  width: 20px; height: 20px; border-radius: 50%;
  border: 2px solid #e2e8f0; border-top-color: #E31937;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.card { background: white; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid #f0f0f0; overflow: hidden; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 1rem 1.25rem; text-align: left; border-bottom: 1px solid #f1f5f9; }
.data-table th { color: #94a3b8; font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; background: #f8fafc; }
.font-bold { font-weight: 600; color: #1a1a1a; }
.period-badge { font-size: 0.82rem; padding: 0.35rem 0.6rem; background: #f8f9fa; border: 1px solid #e2e8f0; border-radius: 6px; display: inline-flex; align-items: center; gap: 0.4rem; margin: 0.2rem; flex-wrap: wrap; }
.type-tag { font-weight: 700; color: #0369a1; text-transform: uppercase; font-size: 0.72rem; background: #e0f2fe; padding: 1px 6px; border-radius: 4px; }
.reason-tag { color: #854d0e; font-style: italic; }
.empty { text-align: center; color: #94a3b8; padding: 3rem !important; }
</style>
