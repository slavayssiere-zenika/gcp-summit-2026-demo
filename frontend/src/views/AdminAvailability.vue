<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { Calendar } from 'lucide-vue-next'

const users = ref<any[]>([])
const isLoading = ref(true)

const fetchUsers = async () => {
    try {
        const token = localStorage.getItem('access_token')
        const response = await axios.get('/users-api/?limit=100', {
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
  <div class="admin-availability">
     <h1><Calendar /> Vue Synthétique des Indisponibilités</h1>
     <p class="desc">Aperçu RH des congés, arrêts et staffings chez les clients pour optimiser les affectations de missions.</p>
     <div v-if="isLoading" class="loading">Chargement des agendas...</div>
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
.admin-availability { padding: 2rem; max-width: 1200px; margin: 0 auto; animation: fadeIn 0.4s; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
h1 { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; font-size: 2rem; color: #1a1a1a; font-weight: 800; }
.desc { color: #666; margin-bottom: 2rem; font-size: 1.05rem; }
.card { background: white; padding: 1.5rem; border-radius: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #f0f0f0;}
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 1rem; text-align: left; border-bottom: 1px solid #eee; }
.data-table th { color: #999; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; }
.font-bold { font-weight: 600; color: #1a1a1a; }
.period-badge { font-size: 0.85rem; padding: 0.4rem 0.6rem; background: #f8f9fa; border: 1px solid #ddd; border-radius: 6px; display: inline-flex; align-items: center; gap: 0.5rem; margin: 0.2rem; }
.type-tag { font-weight: bold; color: #0369a1; text-transform: uppercase; font-size: 0.75rem; }
.reason-tag { color: #854d0e; font-style: italic; }
.empty { text-align: center; color: #999; padding: 2rem !important; }
</style>
