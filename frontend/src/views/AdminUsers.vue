<template>
  <div class="admin-users-wrapper fade-in">
    <div class="header-banner">
      <div class="banner-icon"><Users size="32" /></div>
      <div class="banner-text">
        <h2>Gestion des Accès</h2>
        <p>Gérez les droits d'administration et le statut des utilisateurs de la plateforme.</p>
      </div>
    </div>

    <div class="glass-panel">
      <div class="panel-header">
        <h3><Network size="20" /> Annuaire des Utilisateurs</h3>
        <button class="action-btn-small" @click="fetchUsers" :disabled="isLoading">
          <RefreshCw :class="{ spin: isLoading }" size="16" /> Rafraîchir
        </button>
      </div>
      
      <div class="panel-body">
        <div v-if="error" class="error-panel">
          <strong>Erreur :</strong> {{ error }}
        </div>

        <div class="table-container">
          <table class="data-table" v-if="users.length > 0">
            <thead>
              <tr>
                <th>ID</th>
                <th>Utilisateur</th>
                <th>Email</th>
                <th>Statut</th>
                <th>Rôle</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in users" :key="user.id">
                <td class="font-mono text-sm">#{{ user.id }}</td>
                <td>
                  <strong>{{ user.full_name || user.username }}</strong>
                  <div class="text-sm text-gray">@{{ user.username }}</div>
                </td>
                <td>{{ user.email }}</td>
                <td>
                  <span class="status-badge" :class="user.is_active ? 'active' : 'inactive'">
                    <CheckCircle2 v-if="user.is_active" size="14" />
                    <XCircle v-else size="14" />
                    {{ user.is_active ? 'Actif' : 'Inactif' }}
                  </span>
                </td>
                <td>
                  <span class="role-badge" :class="user.role">
                    <ShieldCheck v-if="user.role === 'admin'" size="14" />
                    <Shield v-else-if="user.role === 'rh'" size="14" />
                    <Briefcase v-else-if="user.role === 'commercial'" size="14" />
                    <UserIcon v-else size="14" />
                    {{ user.role === 'admin' ? 'Administrateur' : (user.role === 'rh' ? 'RH' : (user.role === 'commercial' ? 'Commercial' : 'Utilisateur')) }}
                  </span>
                </td>
                <td>
                  <div class="quick-actions">
                    <div class="role-selector">
                      <button 
                        @click="setRole(user, 'user')" 
                        class="btn-mini" 
                        :class="{ 'active': user.role === 'user' }"
                        title="Utilisateur"
                        :disabled="isUpdating === user.id"
                      >
                        U
                      </button>
                      <button 
                        @click="setRole(user, 'rh')" 
                        class="btn-mini btn-rh" 
                        :class="{ 'active': user.role === 'rh' }"
                        title="RH"
                        :disabled="isUpdating === user.id"
                      >
                        RH
                      </button>
                      <button 
                        @click="setRole(user, 'commercial')" 
                        class="btn-mini btn-commercial" 
                        :class="{ 'active': user.role === 'commercial' }"
                        title="Commercial"
                        :disabled="isUpdating === user.id"
                      >
                        CO
                      </button>
                      <button 
                        @click="setRole(user, 'admin')" 
                        class="btn-mini btn-admin" 
                        :class="{ 'active': user.role === 'admin' }"
                        title="Administrateur"
                        :disabled="isUpdating === user.id"
                      >
                        AD
                      </button>
                    </div>
                    <button 
                      @click="toggleStatus(user)" 
                      class="btn-icon" 
                      :class="user.is_active ? 'btn-danger' : 'btn-success'"
                      :title="user.is_active ? 'Désactiver le compte' : 'Activer le compte'"
                      :disabled="isUpdating === user.id"
                    >
                      <UserX v-if="user.is_active" size="16" />
                      <UserCheck v-else size="16" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-if="users.length === 0 && !isLoading" class="empty-state">
            <Users class="empty-icon" />
            <p>Aucun utilisateur trouvé.</p>
          </div>
          
          <div v-if="isLoading && users.length === 0" class="loading-state">
            <Loader2 class="spinner" size="32" />
            <p>Chargement des utilisateurs...</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import {
  Users, RefreshCw, Network, ShieldCheck, ShieldAlert, Shield, Briefcase,
  User as UserIcon, CheckCircle2, XCircle, UserX, UserCheck, Loader2
} from 'lucide-vue-next'

const users = ref<any[]>([])
const isLoading = ref(false)
const error = ref('')
const isUpdating = ref<number | null>(null)

const fetchUsers = async () => {
  isLoading.value = true
  error.value = ''
  try {
    const response = await axios.get('/auth/?skip=0&limit=100')
    if (response.data && response.data.items) {
      users.value = response.data.items
    }
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || "Erreur de chargement"
  } finally {
    isLoading.value = false
  }
}

const setRole = async (user: any, newRole: string) => {
  if (user.role === newRole) return
  if (!confirm(`Confirmez-vous le passage au rôle ${newRole} pour ${user.username} ?`)) return
  
  isUpdating.value = user.id
  error.value = ''
  try {
    await axios.put(`/auth/${user.id}`, { role: newRole })
    user.role = newRole
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || "Erreur de mise à jour"
  } finally {
    isUpdating.value = null
  }
}

const toggleStatus = async (user: any) => {
  if (!confirm(`Confirmez-vous le changement de statut pour ${user.username} ?`)) return
  
  isUpdating.value = user.id
  error.value = ''
  try {
    const newStatus = !user.is_active
    await axios.put(`/auth/${user.id}`, { is_active: newStatus })
    user.is_active = newStatus
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || "Erreur de mise à jour"
  } finally {
    isUpdating.value = null
  }
}

onMounted(() => {
  fetchUsers()
})
</script>

<style scoped>
.admin-users-wrapper {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem;
}

.header-banner {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-radius: 20px;
  padding: 2.5rem;
  color: white;
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 2.5rem;
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.2);
}

.banner-icon {
  background: rgba(227, 25, 55, 0.2);
  padding: 1.25rem;
  border-radius: 16px;
  color: var(--zenika-red);
}

.banner-text h2 {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0 0 0.5rem 0;
}

.banner-text p {
  color: #94a3b8;
  margin: 0;
  font-size: 1.05rem;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(20px);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  padding: 2rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.panel-header h3 {
  font-size: 1.25rem;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}
.panel-header h3 svg {
  color: var(--zenika-red);
}

.action-btn-small {
  background: rgba(0,0,0,0.05);
  border: 1px solid rgba(0,0,0,0.1);
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  color: #475569;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
}

.action-btn-small:hover {
  background: white;
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

.data-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  margin-bottom: 1rem;
}

.data-table th {
  background: #f8fafc;
  padding: 1rem;
  text-align: left;
  font-size: 0.85rem;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 2px solid #e2e8f0;
}

.data-table th:first-child { border-top-left-radius: 12px; border-bottom-left-radius: 12px; }
.data-table th:last-child { border-top-right-radius: 12px; border-bottom-right-radius: 12px; }

.data-table td {
  padding: 1.25rem 1rem;
  border-bottom: 1px solid #f1f5f9;
  color: #334155;
  font-size: 0.95rem;
  vertical-align: middle;
}

.data-table tr:hover td {
  background: #fdfdfd;
}

.text-gray { color: #94a3b8; }
.font-mono { font-family: 'JetBrains Mono', monospace; }
.text-sm { font-size: 0.875rem; }

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}
.status-badge.active {
  background: #ecfdf5; color: #059669; border: 1px solid #d1fae5;
}
.status-badge.inactive {
  background: #fef2f2; color: #ef4444; border: 1px solid #fee2e2;
}

.role-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}
.role-badge.admin {
  background: rgba(227, 25, 55, 0.1); color: var(--zenika-red); border: 1px solid rgba(227, 25, 55, 0.2);
}
.role-badge.rh {
  background: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.2);
}
.role-badge.commercial {
  background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.2);
}
.role-badge.user {
  background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0;
}

.quick-actions {
  display: flex;
  gap: 8px;
}

.btn-icon, .btn-mini {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #f8fafc;
}
.btn-icon:disabled, .btn-mini:disabled { opacity: 0.5; cursor: not-allowed; }

.role-selector {
  display: flex;
  gap: 4px;
}

.btn-mini {
  width: 28px;
  height: 28px;
  font-size: 0.7rem;
  font-weight: 700;
  color: #94a3b8;
  border-color: #e2e8f0;
}

.btn-mini.active {
  background: #94a3b8;
  color: white;
  border-color: #94a3b8;
  cursor: default;
}

.btn-mini.btn-rh.active {
  background: #3b82f6;
  border-color: #3b82f6;
}

.btn-mini.btn-commercial.active {
  background: #f59e0b;
  border-color: #f59e0b;
}

.btn-mini.btn-admin.active {
  background: var(--zenika-red);
  border-color: var(--zenika-red);
}

.btn-mini:hover:not(.active):not(:disabled) {
  background: #f1f5f9;
  border-color: #cbd5e1;
}

.btn-primary-ghost { color: #3b82f6; border-color: #bfdbfe; }
.btn-primary-ghost:hover:not(:disabled) { background: #eff6ff; }

.btn-warning { color: #f59e0b; border-color: #fde68a; }
.btn-warning:hover:not(:disabled) { background: #fffbeb; }

.btn-success { color: #10b981; border-color: #a7f3d0; }
.btn-success:hover:not(:disabled) { background: #ecfdf5; }

.btn-danger { color: #ef4444; border-color: #fecaca; }
.btn-danger:hover:not(:disabled) { background: #fef2f2; }

.error-panel {
  margin-bottom: 2rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 1.25rem;
  border-radius: 12px;
  color: #b91c1c;
  display: flex;
  gap: 10px;
}

.empty-state, .loading-state {
  text-align: center;
  padding: 4rem 0;
  color: #94a3b8;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}
.empty-icon { opacity: 0.5; width: 48px; height: 48px; }

.spin, .spinner { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

.fade-in { animation: fadeIn 0.4s ease forwards; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
</style>
