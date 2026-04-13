<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { Users, Search, Shield, ShieldOff, CheckCircle2, XCircle } from 'lucide-vue-next'

const query = ref('')
const users = ref<any[]>([])
const isLoading = ref(false)
const error = ref('')
const actionMessage = ref<{ type: 'success' | 'error', text: string } | null>(null)

const searchUsers = async () => {
  if (query.value.trim().length === 0) {
    users.value = []
    actionMessage.value = null
    return
  }
  
  isLoading.value = true
  error.value = ''
  actionMessage.value = null
  
  try {
    const resp = await axios.get(`/auth/search`, {
      params: { query: query.value, limit: 10 }
    })
    users.value = resp.data.items
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || "Erreur de recherche"
  } finally {
    isLoading.value = false
  }
}

const setRole = async (user: any, newRole: string) => {
  if (user.role === newRole) return
  
  const actionText = `changer le rôle de ${user.username} en ${newRole}`
  
  if (!confirm(`Voulez-vous vraiment ${actionText} ?`)) {
    return
  }
  
  actionMessage.value = null
  
  try {
    const resp = await axios.put(`/auth/${user.id}`, { role: newRole })
    user.role = resp.data.role
    
    actionMessage.value = {
      type: 'success',
      text: `Le rôle de ${user.username} a été mis à jour avec succès (${newRole}).`
    }
  } catch (e: any) {
    actionMessage.value = {
      type: 'error',
      text: e.response?.data?.detail || e.message || `Impossible de modifier les droits.`
    }
  }
}
</script>

<template>
  <div class="glass-panel">
    <div class="panel-header">
      <h3><Users size="20" /> Gestion des Rôles Administrateurs</h3>
    </div>
    <div class="panel-body">
      <p class="description">
        Recherchez un utilisateur pour modifier ses privilèges. Un administrateur a un accès complet aux outils sensibles et à la facturation liée à Gemini.
      </p>

      <div class="search-bar">
        <Search size="18" class="search-icon" />
        <input 
          type="text" 
          v-model="query" 
          @keyup.enter="searchUsers" 
          placeholder="Rechercher par pseudo ou email..."
          class="search-input"
        />
        <button @click="searchUsers" class="action-btn small-btn" :disabled="isLoading">
          Chercher
        </button>
      </div>

      <div v-if="error" class="error-text">{{ error }}</div>

      <div v-if="actionMessage" :class="['action-message', `message-${actionMessage.type}`]">
        <CheckCircle2 v-if="actionMessage.type === 'success'" size="18" />
        <XCircle v-else size="18" />
        {{ actionMessage.text }}
      </div>

      <div class="users-list" v-if="users.length > 0">
        <div v-for="user in users" :key="user.id" class="user-card">
          <div class="user-info">
            <span class="user-name">{{ user.full_name || user.username }}</span>
            <span class="user-email">{{ user.email }}</span>
          </div>
          
          <div class="user-role-badge" :class="{'admin-role': user.role === 'admin', 'rh-role': user.role === 'rh'}">
            {{ user.role }}
          </div>
          
          <div class="role-actions">
            <button 
              @click="setRole(user, 'user')" 
              class="role-btn" 
              :class="{'active': user.role === 'user'}"
              title="Passer en Utilisateur standard"
            >
              U
            </button>
            <button 
              @click="setRole(user, 'rh')" 
              class="role-btn rh-btn" 
              :class="{'active': user.role === 'rh'}"
              title="Passer en RH"
            >
              RH
            </button>
            <button 
              @click="setRole(user, 'admin')" 
              class="role-btn admin-btn" 
              :class="{'active': user.role === 'admin'}"
              title="Passer en Admin"
            >
              AD
            </button>
          </div>
        </div>
      </div>
      
      <div v-if="users.length === 0 && query && !isLoading" class="no-results">
        Aucun utilisateur trouvé pour cette recherche.
      </div>
    </div>
  </div>
</template>

<style scoped>
.glass-panel {
  background: rgba(255, 255, 255, 0.5);
  backdrop-filter: blur(20px);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  padding: 2rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

.panel-header h3 {
  font-size: 1.25rem;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 1.5rem 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.panel-header h3 svg {
  color: var(--zenika-red);
}

.description {
  color: #475569;
  font-size: 1rem;
  line-height: 1.6;
  margin-bottom: 1.5rem;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
  position: relative;
}

.search-icon {
  position: absolute;
  left: 1rem;
  color: #94a3b8;
}

.search-input {
  flex: 1;
  padding: 0.8rem 1rem 0.8rem 2.8rem;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  font-size: 1rem;
  outline: none;
  transition: all 0.2s;
  background: white;
}

.search-input:focus {
  border-color: var(--zenika-red);
  box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1);
}

.action-btn {
  background: var(--zenika-red);
  color: white;
  border: none;
  border-radius: 12px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
}

.small-btn {
  padding: 0.8rem 1.5rem;
  font-size: 0.95rem;
}

.action-btn:hover:not(:disabled) {
  background: #c3132e;
}

.action-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.error-text {
  color: #ef4444;
  margin-bottom: 1rem;
  font-size: 0.9rem;
}

.action-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 1rem;
  border-radius: 12px;
  margin-bottom: 1.5rem;
  font-size: 0.95rem;
  font-weight: 500;
}

.message-success {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.message-error {
  background: rgba(239, 68, 68, 0.1);
  color: #b91c1c;
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.users-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.user-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  background: white;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  transition: all 0.2s;
}

.user-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.user-info {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.user-name {
  font-weight: 600;
  color: #1e293b;
}

.user-email {
  font-size: 0.85rem;
  color: #64748b;
}

.user-role-badge {
  padding: 0.3rem 0.8rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  background: #f1f5f9;
  color: #64748b;
  margin-right: 1.5rem;
}

.user-role-badge.admin-role {
  background: rgba(227, 25, 55, 0.1);
  color: var(--zenika-red);
}

.user-role-badge.rh-role {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.role-actions {
  display: flex;
  gap: 6px;
}

.role-btn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: white;
  color: #64748b;
  font-size: 0.75rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.role-btn:hover:not(.active) {
  background: #f8fafc;
  border-color: #cbd5e1;
}

.role-btn.active {
  cursor: default;
}

.role-btn.active:not(.rh-btn):not(.admin-btn) {
  background: #64748b;
  color: white;
  border-color: #64748b;
}

.role-btn.rh-btn.active {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.role-btn.admin-btn.active {
  background: var(--zenika-red);
  color: white;
  border-color: var(--zenika-red);
}

.no-results {
  text-align: center;
  padding: 2rem;
  color: #64748b;
  font-size: 0.95rem;
  background: rgba(241, 245, 249, 0.5);
  border-radius: 12px;
}
</style>
