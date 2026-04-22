<template>
  <div class="admin-users-wrapper fade-in">
    <div class="header-banner">
      <div class="banner-icon"><Users size="32" /></div>
      <div class="banner-text">
        <h2>Gestion des Utilisateurs</h2>
        <p>Annuaire global : gérez les rôles, les accès et visualisez la répartition géographique (Agences).</p>
      </div>
    </div>

    <div class="glass-panel">
      <!-- Toolbar: Search & Filters -->
      <div class="toolbar">
        <div class="search-box">
          <Search class="search-icon" size="18" />
          <input 
            type="text" 
            v-model="searchQuery" 
            placeholder="Rechercher par nom, email..." 
          />
        </div>
        
        <div class="filters">
          <div class="filter-group">
            <Filter size="16" class="filter-icon" />
            <select v-model="selectedAgency" class="filter-select">
              <option value="">Toutes les agences</option>
              <option v-for="agency in availableAgencies" :key="agency" :value="agency">
                {{ agency }}
              </option>
            </select>
          </div>
          
          <div class="filter-group">
            <Shield size="16" class="filter-icon" />
            <select v-model="selectedRole" class="filter-select">
              <option value="">Tous les rôles</option>
              <option value="admin">Admin</option>
              <option value="rh">RH</option>
              <option value="commercial">Commercial</option>
              <option value="user">Utilisateur</option>
            </select>
          </div>
        </div>

        <button class="action-btn-small" @click="fetchUsers" :disabled="isLoading">
          <RefreshCw :class="{ spin: isLoading }" size="16" />
        </button>
      </div>
      
      <div class="panel-body">
        <div v-if="error" class="error-panel">
          <strong>Erreur :</strong> {{ error }}
        </div>

        <div class="table-container">
          <table class="data-table" v-if="paginatedUsers.length > 0">
            <thead>
              <tr>
                <th>Utilisateur</th>
                <th>Rôle</th>
                <th>Statut</th>
                <th>Agence</th>
                <th class="actions-col">Actions Rapides</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in paginatedUsers" :key="user.id" :class="{ 'row-inactive': !user.is_active }">
                <td>
                  <div class="user-profile">
                    <div class="avatar">
                      <img v-if="user.picture_url" :src="user.picture_url" alt="" />
                      <span v-else>{{ getInitials(user.full_name || user.username) }}</span>
                    </div>
                    <div class="user-info">
                      <strong>{{ user.full_name || user.username }}</strong>
                      <span class="user-email">{{ user.email }}</span>
                    </div>
                  </div>
                </td>
                <td>
                  <span class="role-badge" :class="user.role">
                    <ShieldCheck v-if="user.role === 'admin'" size="14" />
                    <Shield v-else-if="user.role === 'rh'" size="14" />
                    <Briefcase v-else-if="user.role === 'commercial'" size="14" />
                    <UserIcon v-else size="14" />
                    {{ formatRole(user.role) }}
                  </span>
                </td>
                <td>
                  <span class="status-badge" :class="user.is_active ? 'active' : 'inactive'">
                    <CheckCircle2 v-if="user.is_active" size="14" />
                    <XCircle v-else size="14" />
                    {{ user.is_active ? 'Actif' : 'Désactivé' }}
                  </span>
                </td>
                <td>
                  <span class="agency-tag" v-if="getPrimaryAgency(user)">
                    {{ getPrimaryAgency(user) }}
                  </span>
                  <span class="text-gray text-sm" v-else>Non assignée</span>
                </td>
                <td class="actions-col">
                  <div class="quick-actions">
                    <div class="role-selector">
                      <button @click="setRole(user, 'user')" class="btn-mini" :class="{ 'active': user.role === 'user' }" title="Utilisateur" :disabled="isUpdating === user.id">U</button>
                      <button @click="setRole(user, 'rh')" class="btn-mini btn-rh" :class="{ 'active': user.role === 'rh' }" title="RH" :disabled="isUpdating === user.id">RH</button>
                      <button @click="setRole(user, 'commercial')" class="btn-mini btn-commercial" :class="{ 'active': user.role === 'commercial' }" title="Commercial" :disabled="isUpdating === user.id">CO</button>
                      <button @click="setRole(user, 'admin')" class="btn-mini btn-admin" :class="{ 'active': user.role === 'admin' }" title="Administrateur" :disabled="isUpdating === user.id">AD</button>
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

          <!-- Empty States -->
          <div v-if="users.length > 0 && paginatedUsers.length === 0" class="empty-state">
            <Search class="empty-icon" />
            <p>Aucun utilisateur ne correspond à vos filtres.</p>
          </div>
          
          <div v-if="users.length === 0 && !isLoading" class="empty-state">
            <Users class="empty-icon" />
            <p>Aucun utilisateur trouvé dans la base de données.</p>
          </div>
          
          <div v-if="isLoading && users.length === 0" class="loading-state">
            <Loader2 class="spinner" size="32" />
            <p>Chargement des {{ totalUsersCount ? totalUsersCount : '' }} utilisateurs...</p>
          </div>
        </div>
      </div>
      
      <!-- Pagination Controls -->
      <div class="pagination" v-if="totalPages > 1">
        <span class="pagination-info">
          Affichage {{ (currentPage - 1) * itemsPerPage + 1 }} - {{ Math.min(currentPage * itemsPerPage, filteredUsers.length) }} sur {{ filteredUsers.length }}
        </span>
        <div class="pagination-buttons">
          <button @click="currentPage--" :disabled="currentPage === 1" class="page-btn"><ChevronLeft size="16" /></button>
          <span class="page-current">Page {{ currentPage }} / {{ totalPages }}</span>
          <button @click="currentPage++" :disabled="currentPage === totalPages" class="page-btn"><ChevronRight size="16" /></button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import {
  Users, RefreshCw, ShieldCheck, Shield, Briefcase,
  User as UserIcon, CheckCircle2, XCircle, UserX, UserCheck, Loader2,
  Search, Filter, ChevronLeft, ChevronRight
} from 'lucide-vue-next'

const users = ref<any[]>([])
const isLoading = ref(false)
const error = ref('')
const isUpdating = ref<number | null>(null)
const totalUsersCount = ref<number>(0)

// Filters & Pagination state
const searchQuery = ref('')
const selectedRole = ref('')
const selectedAgency = ref('')
const currentPage = ref(1)
const itemsPerPage = 15

const fetchUsers = async () => {
  isLoading.value = true
  error.value = ''
  try {
    // Fetch users in chunks since API limits to 100 max per request
    let allUsers: any[] = []
    let skip = 0
    let limit = 100
    let total = 0
    let hasMore = true
    
    while (hasMore) {
      const response = await axios.get(`/auth/?skip=${skip}&limit=${limit}`)
      if (response.data && response.data.items) {
        allUsers = [...allUsers, ...response.data.items]
        total = response.data.total || allUsers.length
        
        if (allUsers.length >= total || response.data.items.length < limit) {
          hasMore = false
        } else {
          skip += limit
        }
      } else {
        hasMore = false
      }
    }
    
    users.value = allUsers
    totalUsersCount.value = total
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || "Erreur de chargement"
  } finally {
    isLoading.value = false
  }
}

const categories = ref<any[]>([])
const userTagsMap = ref<Record<string, string>>({})

const fetchUserTags = async () => {
  try {
    const response = await axios.get('/api/cv/users/tags/map')
    userTagsMap.value = response.data || {}
  } catch (err) {
    console.error('Failed to fetch user tags mapping:', err)
  }
}

const fetchCategories = async () => {
  try {
    const response = await axios.get('/api/items/categories')
    categories.value = response.data.items || []
  } catch (err) {
    console.error('Failed to fetch categories:', err)
  }
}

const getCategoryName = (id: number) => {
  const cat = categories.value.find(c => c.id === id)
  return cat ? cat.name : `Agence #${id}`
}

const getPrimaryAgency = (user: any) => {
  if (!user || !user.id) return null
  return userTagsMap.value[user.id.toString()] || null
}

const availableAgencies = computed(() => {
  const SetOfAgencies = new Set<string>()
  users.value.forEach(u => {
    const primary = getPrimaryAgency(u)
    if (primary) SetOfAgencies.add(primary)
  })
  return Array.from(SetOfAgencies).sort()
})

const filteredUsers = computed(() => {
  let result = users.value

  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(u => 
      (u.full_name && u.full_name.toLowerCase().includes(q)) ||
      (u.email && u.email.toLowerCase().includes(q)) ||
      (u.username && u.username.toLowerCase().includes(q))
    )
  }

  if (selectedRole.value) {
    result = result.filter(u => u.role === selectedRole.value)
  }

  if (selectedAgency.value) {
    result = result.filter(u => {
      const primary = getPrimaryAgency(u)
      return primary === selectedAgency.value
    })
  }

  return result
})

const totalPages = computed(() => Math.ceil(filteredUsers.value.length / itemsPerPage))

const paginatedUsers = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  return filteredUsers.value.slice(start, start + itemsPerPage)
})

const getInitials = (name: string) => {
  if (!name) return '?'
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase()
}

const formatRole = (role: string) => {
  const map: Record<string, string> = {
    'admin': 'Administrateur',
    'rh': 'RH',
    'commercial': 'Commercial',
    'user': 'Utilisateur'
  }
  return map[role] || role
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

// Ensure pagination resets if filtering causes out-of-bounds
computed(() => {
  if (currentPage.value > totalPages.value && totalPages.value > 0) {
    currentPage.value = totalPages.value
  }
})

onMounted(() => {
  fetchCategories()
  fetchUserTags()
  fetchUsers()
})
</script>

<style scoped>
.admin-users-wrapper {
  max-width: 1200px;
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
  margin-bottom: 2rem;
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
  padding: 1.5rem 2rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

/* Toolbar & Filters */
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  gap: 1rem;
  flex-wrap: wrap;
}

.search-box {
  position: relative;
  flex: 1;
  min-width: 250px;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: #94a3b8;
}

.search-box input {
  width: 100%;
  padding: 0.75rem 1rem 0.75rem 2.5rem;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: white;
  font-size: 0.95rem;
  transition: all 0.2s;
}

.search-box input:focus {
  outline: none;
  border-color: var(--zenika-red);
  box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.1);
}

.filters {
  display: flex;
  gap: 1rem;
}

.filter-group {
  position: relative;
  display: flex;
  align-items: center;
}

.filter-icon {
  position: absolute;
  left: 12px;
  color: #64748b;
  pointer-events: none;
}

.filter-select {
  padding: 0.75rem 2.5rem 0.75rem 2.5rem;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: white;
  font-size: 0.9rem;
  font-weight: 500;
  color: #334155;
  cursor: pointer;
  appearance: none;
  min-width: 170px;
}

.filter-select:focus {
  outline: none;
  border-color: #94a3b8;
}

.action-btn-small {
  background: white;
  border: 1px solid #e2e8f0;
  padding: 0.75rem;
  border-radius: 12px;
  color: #475569;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: all 0.2s ease;
}

.action-btn-small:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

/* User Profile Row */
.user-profile {
  display: flex;
  align-items: center;
  gap: 12px;
}

.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #e2e8f0, #cbd5e1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #475569;
  overflow: hidden;
  flex-shrink: 0;
}

.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.user-info {
  display: flex;
  flex-direction: column;
}

.user-info strong {
  font-size: 0.95rem;
  color: #1e293b;
}

.user-email {
  font-size: 0.8rem;
  color: #64748b;
}

.agency-tag {
  background: rgba(227, 25, 55, 0.1);
  color: var(--zenika-red);
  padding: 4px 10px;
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 600;
  display: inline-block;
  border: 1px solid rgba(227, 25, 55, 0.2);
}

/* Table Enhancements */
.table-container {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 8px;
  margin-bottom: 1rem;
}

.data-table th {
  padding: 0 1rem 0.5rem 1rem;
  text-align: left;
  font-size: 0.85rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 2px solid #e2e8f0;
}

.data-table td {
  padding: 1rem;
  background: white;
  border-top: 1px solid #f1f5f9;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
}

.data-table tr td:first-child {
  border-left: 1px solid #f1f5f9;
  border-top-left-radius: 12px;
  border-bottom-left-radius: 12px;
}

.data-table tr td:last-child {
  border-right: 1px solid #f1f5f9;
  border-top-right-radius: 12px;
  border-bottom-right-radius: 12px;
}

.data-table tr:hover td {
  background: #fdfdfd;
  box-shadow: 0 4px 12px rgba(0,0,0,0.02);
}

.row-inactive td {
  opacity: 0.7;
  background: #fafafa;
}

.actions-col {
  text-align: right;
  width: 220px;
}

.quick-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

/* Reusing Roles & Status Styling */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}
.status-badge.active { background: #ecfdf5; color: #059669; border: 1px solid #d1fae5; }
.status-badge.inactive { background: #fef2f2; color: #ef4444; border: 1px solid #fee2e2; }

.role-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}
.role-badge.admin { background: rgba(227, 25, 55, 0.1); color: var(--zenika-red); border: 1px solid rgba(227, 25, 55, 0.2); }
.role-badge.rh { background: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.2); }
.role-badge.commercial { background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.2); }
.role-badge.user { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }

.role-selector { display: flex; gap: 4px; }
.btn-mini {
  width: 26px; height: 26px; font-size: 0.65rem; font-weight: 700; color: #94a3b8;
  border: 1px solid #e2e8f0; border-radius: 6px; background: white; cursor: pointer; transition: all 0.2s;
}
.btn-mini.active { background: #94a3b8; color: white; border-color: #94a3b8; cursor: default; }
.btn-mini.btn-rh.active { background: #3b82f6; border-color: #3b82f6; }
.btn-mini.btn-commercial.active { background: #f59e0b; border-color: #f59e0b; }
.btn-mini.btn-admin.active { background: var(--zenika-red); border-color: var(--zenika-red); }
.btn-mini:hover:not(.active):not(:disabled) { background: #f1f5f9; border-color: #cbd5e1; }

.btn-icon {
  width: 28px; height: 28px; border-radius: 6px; border: 1px solid transparent;
  display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.2s; background: white;
}
.btn-success { color: #10b981; border-color: #a7f3d0; }
.btn-success:hover { background: #ecfdf5; }
.btn-danger { color: #ef4444; border-color: #fecaca; }
.btn-danger:hover { background: #fef2f2; }

/* Pagination */
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.pagination-info {
  font-size: 0.85rem;
  color: #64748b;
  font-weight: 500;
}

.pagination-buttons {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.page-btn {
  background: white;
  border: 1px solid #e2e8f0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:hover:not(:disabled) {
  background: #f8fafc;
  color: #1e293b;
  border-color: #cbd5e1;
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-current {
  font-size: 0.85rem;
  font-weight: 600;
  color: #334155;
}

.error-panel {
  margin-bottom: 2rem;
  background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 1.25rem; border-radius: 12px; color: #b91c1c;
}

.empty-state, .loading-state {
  text-align: center; padding: 4rem 0; color: #94a3b8;
  display: flex; flex-direction: column; align-items: center; gap: 1rem;
}
.empty-icon { opacity: 0.5; width: 48px; height: 48px; }
.spin, .spinner { animation: spin 1s linear infinite; }

@keyframes spin { 100% { transform: rotate(360deg); } }
.fade-in { animation: fadeIn 0.4s ease forwards; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.text-gray { color: #94a3b8; }
.text-sm { font-size: 0.85rem; }
</style>
