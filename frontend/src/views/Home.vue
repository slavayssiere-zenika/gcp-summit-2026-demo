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
import MissionCard from '@/components/agent/MissionCard.vue'
import ConsultantCard from '@/components/agent/ConsultantCard.vue'
import ItemCard from '@/components/agent/ItemCard.vue'
import ToolExecutionList from '@/components/agent/ToolExecutionList.vue'
import CandidateProfileCard from '@/components/agent/CandidateProfileCard.vue'
import SystemHealthCard from '@/components/agent/SystemHealthCard.vue'

const isHealthComponent = (obj: any) => obj && typeof obj.status === 'string' && typeof obj.component === 'string'
const isHealthData = (arr: any[]) => arr && arr.length > 0 && arr.every((o: any) => isHealthComponent(o))

const isUserObj = (obj: any) => obj && obj.email && (obj.username || obj.full_name);
const isItemObj = (obj: any) => obj && obj.name && (obj.categories || obj.owner !== undefined || (obj.user_id && !obj.email));
const isMissionObj = (obj: any) => obj && obj.title && (obj.proposed_team || obj.extracted_competencies || obj.description);
const techKeys = [
  'semantic_embedding', 'raw_content', 'imported_by_id', 'password', 'id', 'user_id', 
  'username', 'name', 'full_name', 'agent', 'response', 'source', 'session_id', 
  'usage', 'thoughts', 'steps', 'dataType', 'displayType', 'parsedData', 'activeTab',
  'result', 'nodes', 'links'
];
const filteredKeys = (obj: any) => obj ? Object.keys(obj).filter(k => !techKeys.includes(k) && !k.startsWith('_')) : [];
const isProfileObj = (obj: any) => obj && !obj.email && (obj.user_id || obj.summary) && (obj.missions || obj.competencies_keywords || obj.current_role)
const isBusinessObj = (obj: any) => isUserObj(obj) || isItemObj(obj) || isMissionObj(obj) || isProfileObj(obj);
const hasBusinessData = (obj: any) => filteredKeys(obj).length > 0 || isBusinessObj(obj);
const hasAnyBusinessData = (msg: any) => {
  if (msg.displayType === 'text_only') return false;
  if (!msg.parsedData || msg.parsedData.length === 0) return false;
  return msg.parsedData.some((obj: any) => hasBusinessData(obj));
};

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
          <div v-if="msg.usage || (msg.displayType && msg.displayType !== 'text_only') || (msg.steps && msg.steps.length > 0) || (msg.thoughts && msg.thoughts.length > 0)" class="message-tabs">
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
            <div v-if="msg.parsedData && (msg.displayType === 'tree' || hasAnyBusinessData(msg) || isHealthData(msg.parsedData))" class="dashboard-content">
              <!-- System Health Dashboard -->
              <SystemHealthCard v-if="isHealthData(msg.parsedData)" :components="msg.parsedData" />

              <!-- Table UI -->
              <div v-else-if="msg.displayType === 'table'" class="data-table-container">
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

              <!-- Dynamic Cards UI (Dedicated Components) -->
              <div v-else-if="msg.displayType === 'cards' && msg.parsedData && msg.parsedData.length > 0"
                   :class="msg.parsedData.every((o: any) => isUserObj(o)) ? 'consultant-list' : 'generic-grid'">
                <template v-for="(obj, idx) in msg.parsedData" :key="idx">
                  <MissionCard v-if="isMissionObj(obj)" :mission="obj" />
                  <ConsultantCard v-else-if="isUserObj(obj)" :consultant="obj" />
                  <CandidateProfileCard v-else-if="isProfileObj(obj)" :profile="obj" />
                  <ItemCard v-else-if="isItemObj(obj)" :item="obj" />
                  
                  <!-- Generic Fallback Card Render -->
                  <div v-else-if="hasBusinessData(obj)" class="generic-dash-card" @click="obj.id || obj.user_id ? goToUser(obj.id || obj.user_id) : null">
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

            <!-- Tool Execution Fallback (When no business visual is shown) -->
            <div v-if="!hasAnyBusinessData(msg) && msg.steps && msg.steps.length > 0">
              <ToolExecutionList :steps="msg.steps" />
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

/* Compact list layout for consultant-only results */
.consultant-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 6px;
  margin-top: 0.75rem;
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

.tree-actions {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  padding: 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.skeleton-wrapper {
  padding: 1rem;
}

.skeleton-row {
  height: 12px;
  background: #edf2f7;
  border-radius: 4px;
  margin-bottom: 10px;
  width: 100%;
  position: relative;
  overflow: hidden;
}

.skeleton-row.header-row {
  height: 20px;
  width: 60%;
  margin-bottom: 20px;
}

.skeleton-row.short {
  width: 40%;
}

.skeleton-row::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.6), transparent);
  animation: loading 1.5s infinite;
}

@keyframes loading {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

</style>
