<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import markdownit from 'markdown-it'
import { 
  Mail, User, Hash, Package, Tag, CheckCircle2, XCircle, Network, Trash2, 
  Eye, Cpu, RefreshCw 
} from 'lucide-vue-next'
import CompetencyNode from '@/components/CompetencyNode.vue'
import { authService } from '@/services/auth'
import { useChatStore } from '@/stores/chatStore'
import AgentExpertTerminal from '@/components/agent/AgentExpertTerminal.vue'
import FinopsBadge from '@/components/agent/FinopsBadge.vue'
import BaseButton from '@/components/ui/BaseButton.vue'

const isUserObj = (obj: any) => obj && obj.email && (obj.username || obj.full_name);
const isItemObj = (obj: any) => obj && obj.name && (obj.categories || obj.owner !== undefined || (obj.user_id && !obj.email));
const techKeys = ['semantic_embedding', 'raw_content', 'imported_by_id', 'password', 'id', 'user_id', 'username', 'name', 'full_name'];
const filteredKeys = (obj: any) => obj ? Object.keys(obj).filter(k => !techKeys.includes(k) && !k.startsWith('_')) : [];

const route = useRoute()
const router = useRouter()
const md = markdownit({
  html: true,
  linkify: true,
  typographer: true
})

const chatStore = useChatStore()
const userInput = ref('')
const chatContainer = ref<HTMLElement | null>(null)

const scrollToBottom = () => {
  setTimeout(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTo({
        top: chatContainer.value.scrollHeight,
        behavior: 'smooth'
      })
    }
  }, 50)
}

const sendQuery = async (queryOverride?: string) => {
  const query = queryOverride || userInput.value.trim()
  if (!query) return
  userInput.value = ''
  await chatStore.sendQuery(query)
  scrollToBottom()
}

const applyTree = async (treeData: any) => {
  await chatStore.applyTree(treeData)
  scrollToBottom()
}

const handleSearch = (queryText: string) => {
  if (!queryText) return
  sendQuery(`cherche l'utilisateur nommé ${queryText}`)
  router.replace({ query: {} })
}

const handleSearchEvent = (event: any) => {
  handleSearch(event.detail)
}

const resetHistory = async () => {
  await chatStore.resetHistory()
}

const goToUser = (id: number) => {
  router.push({ name: 'user-detail', params: { id: id.toString() } })
}

const getInitials = (name: string) => {
  if (!name) return '?'
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

const getPaginatedData = (msg: any) => {
  if (!msg.parsedData || !msg.pagination) return []
  const start = (msg.pagination.currentPage - 1) * msg.pagination.itemsPerPage
  const end = start + msg.pagination.itemsPerPage
  return msg.parsedData.slice(start, end)
}

const totalPages = (msg: any) => {
  if (!msg.parsedData || !msg.pagination) return 0
  return Math.ceil(msg.parsedData.length / msg.pagination.itemsPerPage)
}

const handleInternalLink = (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  const link = target.closest('a');
  if (link) {
    const href = link.getAttribute('href');
    if (href && href.startsWith('user:')) {
      e.preventDefault();
      const userId = parseInt(href.split(':')[1]);
      if (!isNaN(userId)) {
        goToUser(userId);
      }
    }
  }
}

onMounted(() => {
  window.addEventListener('search-user', handleSearchEvent)
  if (chatContainer.value) {
    chatContainer.value.addEventListener('click', handleInternalLink)
  }
  if (route.query.q) {
    handleSearch(route.query.q as string)
  }
  chatStore.fetchHistory().then(() => scrollToBottom())
})

watch(() => route.query.q, (newQ) => {
  if (newQ) {
    handleSearch(newQ as string)
  }
})

onUnmounted(() => {
  window.removeEventListener('search-user', handleSearchEvent)
  if (chatContainer.value) {
    chatContainer.value.removeEventListener('click', handleInternalLink)
  }
})
</script>

<template>
  <div class="chat-wrapper">
    <div class="chat-container" ref="chatContainer">
      <!-- Project Introduction -->
      <div class="welcome-section">
        <h2>Assistant Opérationnel Zenika</h2>
        <p>
          L'Assistant Zenika simplifie la recherche et la gestion des données de l'entreprise. En langage naturel, vous pouvez interroger l'agent pour identifier les meilleurs profils, analyser les cartographies de compétences ou gérer le catalogue d'équipements.
        </p>
        <div class="quick-tips">
          <span>💡 Essayez : "Trouve les consultants spécialisés en Java avec plus de 5 ans d'expérience."</span>
          <span>💡 Essayez : "Recherche les compétences d'Alice et donne-moi un résumé."</span>
        </div>
      </div>

      <div v-for="(msg, index) in chatStore.messages" :key="index" :class="['message', msg.role]">
        <div v-if="msg.role === 'assistant'" class="assistant-content">
          <!-- FinOps Cost Display (Floating Badge) -->
          <div class="usage-container">
            <FinopsBadge :usage="msg.usage" />
          </div>

          <!-- Multi-View Tabs -->
          <div v-if="(msg.displayType && msg.displayType !== 'text_only') || (msg.steps && msg.steps.length > 0) || (msg.thoughts && msg.thoughts.length > 0)" class="message-tabs">
            <button 
              :class="['tab-btn', { active: msg.activeTab === 'preview' }]" 
              @click="msg.activeTab = 'preview'"
            >
              <Eye size="14" /> Aperçu
            </button>
            <button 
              :class="['tab-btn', { active: msg.activeTab === 'expert' }]" 
              @click="msg.activeTab = 'expert'"
            >
              <Cpu size="14" /> Expert
            </button>
          </div>

          <div v-if="msg.activeTab === 'preview' || !msg.activeTab" class="tab-pane">
            <div class="text-content" v-html="md.render(msg.content)"></div>
            
            <!-- Modern JSON Parsed Dashboard -->
            <div v-if="msg.parsedData && (msg.displayType === 'tree' || msg.parsedData.length > 0)" class="dashboard-content">
              <!-- Table UI -->
              <div v-if="msg.displayType === 'table'" class="data-table-container">
                <table class="zen-table">
                  <thead>
                    <tr>
                      <th v-for="key in Object.keys(msg.parsedData[0]).filter(k => !k.startsWith('_'))" :key="key">{{ key.toUpperCase() }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, idx) in getPaginatedData(msg)" :key="idx" @click="row.id || row.user_id ? goToUser(row.id || row.user_id) : null" :class="{ 'clickable-row': row.id || row.user_id }">
                      <td v-for="key in Object.keys(msg.parsedData[0]).filter(k => !k.startsWith('_'))" :key="key">{{ row[key] }}</td>
                    </tr>
                  </tbody>
                </table>
                <!-- Pagination UI -->
                <div v-if="totalPages(msg) > 1" class="pagination-controls">
                  <BaseButton :disabled="msg.pagination!.currentPage === 1" @click="msg.pagination!.currentPage--">Précédent</BaseButton>
                  <span class="page-info">Page {{ msg.pagination!.currentPage }} sur {{ totalPages(msg) }}</span>
                  <BaseButton :disabled="msg.pagination!.currentPage === totalPages(msg)" @click="msg.pagination!.currentPage++">Suivant</BaseButton>
                </div>
              </div>

            <!-- Dynamic Cards UI (Inferred Types) -->
            <div v-else-if="msg.displayType === 'cards'" class="generic-grid">
               <template v-for="(obj, idx) in msg.parsedData" :key="idx">
                 <!-- User Card Render -->
                 <div v-if="isUserObj(obj)" class="user-dash-card clickable" @click="goToUser(obj.id || obj.user_id)">
                    <div class="card-header">
                      <div class="avatar">{{ getInitials(obj.full_name || obj.username) }}</div>
                      <div class="id-tag"><Hash size="12" />{{ obj.id || obj.user_id }}</div>
                    </div>
                    <div class="card-body">
                      <h3 class="name">{{ obj.full_name || obj.username }}</h3>
                      <div class="username" v-if="obj.username">@{{ obj.username }}</div>
                      <div class="email"><Mail size="14" /> {{ obj.email }}</div>
                    </div>
                    <div class="card-footer" v-if="obj.is_active !== undefined">
                      <div :class="['status-pill', obj.is_active ? 'active' : 'inactive']">
                        <CheckCircle2 v-if="obj.is_active" size="14" />
                        <XCircle v-else size="14" />
                        {{ obj.is_active ? 'Actif' : 'Inactif' }}
                      </div>
                    </div>
                 </div>
                 
                 <!-- Item Card Render -->
                 <div v-else-if="isItemObj(obj)" class="item-dash-card">
                    <div class="status-dot-glow"></div>
                    <div class="item-icon-wrapper"><Package size="20" /></div>
                    <div class="item-info">
                       <h4 class="name">{{ obj.name }}</h4>
                      <p class="desc" v-if="obj.description">{{ obj.description }}</p>
                      <div class="owner" v-if="obj.user_id || obj.owner">Propriétaire: #{{ obj.user_id || obj.owner }}</div>
                      <div v-if="obj.categories" class="categories-tags">
                        <span v-for="cat in (Array.isArray(obj.categories) ? obj.categories : [obj.categories])" :key="cat.id || cat" class="tag">
                          <Tag size="10" /> {{ (cat && typeof cat === 'object') ? (cat.name || cat.id) : cat }}
                        </span>
                      </div>
                    </div>
                 </div>

                 <!-- Generic Fallback Card Render -->
                 <div v-else class="generic-dash-card" @click="obj.id || obj.user_id ? goToUser(obj.id || obj.user_id) : null">
                    <div class="card-header" v-if="obj.username || obj.name || obj.full_name">
                      <h3 class="name">{{ obj.full_name || obj.username || obj.name }}</h3>
                      <div v-if="obj.id || obj.user_id" class="id-tag"><Hash size="12" />{{ obj.id || obj.user_id }}</div>
                    </div>
                    <div class="card-body">
                      <div v-for="key in filteredKeys(obj)" :key="key" class="data-row">
                        <strong>{{ key }}:</strong> 
                        <span v-if="!Array.isArray(obj[key]) && typeof obj[key] !== 'object'">{{ obj[key] }}</span>
                        <div v-else class="categories-tags" style="display:inline-flex; flex-wrap:wrap; gap:4px; margin-top:2px;">
                          <span v-for="(item, i) in (Array.isArray(obj[key]) ? obj[key] : [obj[key]])" :key="i" class="tag">
                            {{ (item && typeof item === 'object') ? (item.name || item.id || '[Objet]') : item }}
                          </span>
                        </div>
                      </div>
                    </div>
                 </div>
               </template>
            </div>

            <!-- Tree View UI -->
            <div v-else-if="msg.displayType === 'tree'" class="tree-grid">
               <div class="tree-header">
                 <div style="display: flex; align-items: center; gap: 8px;">
                   <Network size="20" class="tree-icon" /> 
                   <h3>Taxonomie des Compétences</h3>
                 </div>
                 <div v-if="msg.usage?.estimated_cost_usd" class="tree-cost-badge">
                   Coût du recalcule : ${{ Number(msg.usage.estimated_cost_usd).toFixed(4) }}
                 </div>
               </div>
               <div class="tree-content">
                 <div v-for="(node, idx) in (Array.isArray(msg.parsedData) ? msg.parsedData : Object.entries(msg.parsedData).map(([k, v]) => ({ name: k, ...v })))" 
                      :key="idx" 
                      style="margin-bottom: 8px;"
                 >
                   <CompetencyNode :node="node" :depth="0" />
                 </div>
               </div>
               
               <!-- Validation Button for Admin -->
               <div v-if="authService.state.user?.role === 'admin'" class="tree-actions">
                 <BaseButton 
                  @click="applyTree(msg.parsedData)"
                  :loading="chatStore.isTyping"
                 >
                   <CheckCircle2 v-if="!chatStore.isTyping" size="18" />
                   Valider et Appliquer la Taxonomie
                 </BaseButton>
               </div>
            </div>
          </div>
        </div>

          <!-- Expert View Tab (Isolated Component) -->
          <AgentExpertTerminal v-else-if="msg.activeTab === 'expert'" :message="msg" />
        </div>
        
        <div v-else class="user-content">
          {{ msg.content }}
        </div>
      </div>
      
      <div v-if="chatStore.isTyping" class="message assistant typing">
        <!-- Skeleton Loaders UX -->
        <div class="skeleton-wrapper">
          <div class="skeleton-row header-row"></div>
          <div class="skeleton-row"></div>
          <div class="skeleton-row short"></div>
        </div>
      </div>
    </div>

    <div class="input-area">
      <div class="input-container">
        <input 
          type="text" 
          v-model="userInput" 
          @keypress.enter="sendQuery()"
          placeholder="Posez votre question à l'assistant..."
          autocomplete="off"
        >
        <BaseButton @click="resetHistory" variant="ghost" title="Réinitialiser l'historique">
          <Trash2 size="18" />
        </BaseButton>
        <BaseButton @click="sendQuery()" :loading="chatStore.isTyping">Envoyer</BaseButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-wrapper {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 140px);
  background: white;
  border-radius: 24px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.08);
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.message-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #edf2f7;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #64748b;
  padding: 0.4rem 1rem;
  border-radius: 10px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: #e2e8f0;
}

.tab-btn.active {
  background: var(--zenika-red);
  border-color: var(--zenika-red);
  color: white;
  box-shadow: 0 4px 10px rgba(227, 25, 55, 0.2);
}

.cost-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 0.4rem 0.8rem;
  border-radius: 10px;
  font-size: 0.75rem;
  color: #64748b;
  font-weight: 600;
  margin-left: auto; /* Push to the right */
  border-left: 3px solid #10b981;
}

.cost-divider {
  opacity: 0.3;
}

.cost-value {
  color: #059669;
}

.pagination-controls {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border-top: 1px solid #edf2f7;
  background: #f8fafc;
}

.pagination-controls button {
  padding: 0.4rem 0.8rem;
  font-size: 0.8rem;
  border-radius: 8px;
  background: white;
  color: #475569;
  border: 1px solid #e2e8f0;
}

.pagination-controls button:hover:not(:disabled) {
  background: #f1f5f9;
  border-color: #cbd5e0;
}

.pagination-controls button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.8rem;
  color: #64748b;
  font-weight: 600;
}

/* Expert Mode Styles */
.expert-mode {
  animation: fadeIn 0.3s ease-out;
}

.expert-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 1rem;
  color: #475569;
  font-weight: 700;
  font-size: 0.9rem;
}

.steps-timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.step-item {
  display: flex;
  gap: 12px;
  padding: 1rem;
  background: #f8fafc;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
}

.step-item.call {
  border-left: 4px solid var(--zenika-red);
}

.step-item.result {
  border-left: 4px solid #10b981;
}

.step-icon {
  margin-top: 2px;
  color: #475569;
}

.step-details {
  flex: 1;
  overflow: hidden;
}

.step-title {
  font-size: 0.75rem;
  color: #64748b;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.step-payload {
  white-space: pre-wrap;
  word-break: break-all;
  background: #fff;
  padding: 0.75rem;
  border-radius: 8px;
  font-family: inherit;
  font-size: 0.85rem;
  border: 1px solid #f1f5f9;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}

.thought-section {
  margin-bottom: 1.5rem;
}

.thought-bubble {
  background: #f0f4ff;
  border-left: 4px solid #6366f1;
  padding: 1rem;
  border-radius: 0 12px 12px 0;
  font-size: 0.9rem;
  color: #312e81;
  font-style: italic;
  white-space: pre-wrap;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.welcome-section {
  background: linear-gradient(135deg, rgba(227, 25, 55, 0.03) 0%, rgba(255, 255, 255, 1) 100%);
  padding: 1.5rem;
  border-radius: 20px;
  border: 1px solid rgba(227, 25, 55, 0.1);
  margin-bottom: 1rem;
}

.welcome-section h2 {
  font-size: 1.35rem;
  font-weight: 800;
  color: var(--zenika-red);
  margin-bottom: 0.75rem;
  letter-spacing: -0.5px;
}

.welcome-section p {
  color: var(--text-secondary);
  line-height: 1.8;
  margin-bottom: 1.5rem;
  font-size: 1rem;
}

.quick-tips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.quick-tips span {
  background: white;
  border: 1px solid #eee;
  padding: 0.5rem 1rem;
  border-radius: 12px;
  font-size: 0.85rem;
  font-weight: 600;
  color: #555;
  box-shadow: var(--shadow-sm);
  transition: all 0.2s;
  cursor: default;
}

.quick-tips span:hover {
  border-color: var(--zenika-red);
  transform: translateY(-2px);
}

.message {
  max-width: 90%;
  padding: 1.25rem 1.75rem;
  border-radius: 20px;
  line-height: 1.6;
  font-size: 0.95rem;
}

.message.user {
  align-self: flex-end;
  background: var(--zenika-red);
  color: white;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 15px rgba(227, 25, 55, 0.2);
}

.message.assistant {
  align-self: flex-start;
  background: #f8f9fa;
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
  border: 1px solid #edf2f7;
  width: 100%;
}

.dashboard-content {
  margin-top: 1.5rem;
}

/* Dashboard Grids */
.user-grid, .item-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
}

/* User Card */
.user-dash-card {
  background: white;
  border-radius: 20px;
  padding: 1.5rem;
  border: 1px solid #edf2f7;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.user-dash-card.clickable {
  cursor: pointer;
}

.user-dash-card.clickable:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0,0,0,0.06);
  border-color: var(--zenika-red);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.avatar {
  width: 48px;
  height: 48px;
  background: var(--zenika-red);
  color: white;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1.1rem;
  box-shadow: 0 4px 10px rgba(227, 25, 55, 0.2);
}

.id-tag {
  background: #f8f9fa;
  padding: 0.3rem 0.6rem;
  border-radius: 8px;
  font-size: 0.75rem;
  color: #888;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
}

.card-body .name {
  font-size: 1.1rem;
  font-weight: 700;
  margin: 0;
  color: #1a1a1a;
}

.card-body .username {
  font-size: 0.850rem;
  color: #666;
  margin-bottom: 0.75rem;
}

.card-body .email {
  font-size: 0.875rem;
  color: #555;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.card-footer {
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid #f8f9fa;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.8rem;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}

.status-pill.active {
  background: rgba(227, 25, 55, 0.08);
  color: var(--zenika-red);
}

.status-pill.inactive {
  background: #f1f1f1;
  color: #888;
}

/* Item Grid */
.item-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.25rem;
}

.item-dash-card {
  background: #fafafa;
  border-radius: 16px;
  padding: 1rem;
  display: flex;
  gap: 1rem;
  border: 1px solid #eee;
}

.item-icon-wrapper {
  width: 42px;
  height: 42px;
  background: white;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #eee;
  color: var(--zenika-red);
}

.item-info .name {
  font-size: 0.95rem;
  font-weight: 700;
  margin-bottom: 0.25rem;
}

.item-info .desc {
  font-size: 0.825rem;
  color: #666;
  margin-bottom: 0.5rem;
}

.item-info .owner {
  font-size: 0.75rem;
  color: #999;
}

.categories-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.6rem;
}

.tag {
  background: white;
  border: 1px solid #ddd;
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  font-size: 0.7rem;
  color: #555;
  display: flex;
  align-items: center;
  gap: 3px;
}

.input-area {
  padding: 1.5rem 2.5rem 2rem;
  background: white;
  border-top: 1px solid #edf2f7;
}

.input-container {
  display: flex;
  gap: 1rem;
  background: #f8f9fa;
  padding: 0.6rem;
  border-radius: 18px;
  border: 1px solid #e2e8f0;
  transition: all 0.2s;
}

.input-container:focus-within {
  border-color: var(--zenika-red);
  background: white;
  box-shadow: 0 0 0 4px rgba(227, 25, 55, 0.1);
}

input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  padding: 0.75rem 1rem;
  font-size: 1rem;
  color: var(--text-primary);
}

button {
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 0.75rem 1.75rem;
  border-radius: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

button:hover:not(:disabled) {
  background: #c2152f;
  transform: translateY(-1px);
}

.usage-container {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0.5rem;
}

.cost-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(26, 32, 44, 0.03);
  padding: 0.4rem 0.8rem;
  border-radius: 12px;
  font-size: 0.75rem;
  color: #4a5568;
  border: 1px solid rgba(0, 0, 0, 0.03);
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.reset-btn {
  background: white;
  color: #ef4444;
  border: 1px solid #fee2e2;
  padding: 0.75rem 1rem;
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.reset-btn:hover {
  background: #fef2f2;
  color: #dc2626;
  transform: translateY(-1px);
}

.typing span {
  height: 8px;
  width: 8px;
  background: #cbd5e0;
  display: inline-block;
  border-radius: 50%;
  margin: 0 2px;
  animation: bounce 1.3s infinite;
}

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-8px); }
}

.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }

/* Dynamic JSON Dashboard Elements */
.data-table-container {
  overflow-x: auto;
  margin-top: 1.5rem;
  border-radius: 12px;
  border: 1px solid #edf2f7;
  background: white;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
}

.zen-table {
  width: 100%;
  border-collapse: collapse;
}

.zen-table th {
  background: #f8f9fa;
  padding: 1rem;
  text-align: left;
  font-size: 0.75rem;
  color: #64748b;
  font-weight: 700;
  border-bottom: 2px solid #edf2f7;
}

.zen-table td {
  padding: 1rem;
  font-size: 0.875rem;
  border-bottom: 1px solid #edf2f7;
  color: #334155;
}

.zen-table tr:hover {
  background: #f8fafc;
}

.clickable-row {
  cursor: pointer;
  transition: background 0.2s;
}

.clickable-row:hover {
  background: rgba(227, 25, 55, 0.05) !important;
}

.generic-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.25rem;
  margin-top: 1.5rem;
}

.generic-dash-card {
  background: white;
  border-radius: 16px;
  padding: 1.25rem;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
}

.generic-dash-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(227, 25, 55, 0.08);
  border-color: rgba(227, 25, 55, 0.3);
}

.data-row {
  font-size: 0.825rem;
  color: #475569;
  margin-bottom: 0.5rem;
}
.data-row strong {
  color: #1e293b;
  font-weight: 600;
}

/* Tree UI Styles */
.tree-grid {
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(15px);
  border-radius: 16px;
  border: 1px solid rgba(227, 25, 55, 0.1);
  padding: 1.5rem;
  margin-top: 1rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

.tree-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 1.25rem;
  color: var(--zenika-red);
}

.tree-header h3 {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.tree-cost-badge {
  background: rgba(227, 25, 55, 0.1);
  color: var(--zenika-red);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 700;
  margin-left: auto; /* Placer à droite */
}

.json-viewer {
  background: rgba(10, 10, 15, 0.05);
  border-radius: 12px;
  padding: 1.5rem;
  font-family: 'MesloLGS NF', 'Fira Code', monospace;
  font-size: 0.9rem;
  color: var(--text-primary);
  overflow-x: auto;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow: inset 0 2px 8px rgba(0,0,0,0.02);
}
.tree-actions {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  padding: 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.apply-tree-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--zenika-red);
  color: white;
  padding: 12px 24px;
  border-radius: 12px;
  font-weight: 700;
  transition: all 0.3s;
  box-shadow: 0 4px 15px rgba(227, 25, 55, 0.2);
}

.apply-tree-btn:hover:not(:disabled) {
  background: #c2152f;
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(227, 25, 55, 0.3);
}

.apply-tree-btn:disabled {
  opacity: 0.7;
  cursor: wait;
}
</style>
