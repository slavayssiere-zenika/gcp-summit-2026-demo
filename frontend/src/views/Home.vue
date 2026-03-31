<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import markdownit from 'markdown-it'
import { Mail, User, Hash, Package, Tag, CheckCircle2, XCircle, Network } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const md = markdownit({
  html: true,
  linkify: true,
  typographer: true
})

interface Message {
  role: 'user' | 'assistant' | 'error'
  content: string
  data?: any
  parsedData?: any[]
  displayType?: string
  typing?: boolean
}

const messages = ref<Message[]>([
  {
    role: 'assistant',
    content: "Bonjour ! Je suis l'assistant intelligent de Zenika. Je peux orchestrer vos services **Users**, **Items** et **Competencies** pour répondre à vos besoins."
  }
])

const userInput = ref('')
const isTyping = ref(false)
const chatContainer = ref<HTMLElement | null>(null)

const scrollToBottom = () => {
  setTimeout(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  }, 50)
}

const sendQuery = async (queryOverride?: string) => {
  const query = queryOverride || userInput.value.trim()
  if (!query) return

  userInput.value = ''
  messages.value.push({ role: 'user', content: query })
  isTyping.value = true
  scrollToBottom()

  try {
    const response = await axios.post('/api/query', { query })
    isTyping.value = false
    
    let replyText = response.data.response || ''
    let displayType = 'text_only'
    let parsedData = null
    const toolData = response.data.data || null

    try {
      const cleanStr = replyText.replace(/^```json\s*/i, '').replace(/\s*```$/i, '').trim()
      const jsonObj = JSON.parse(cleanStr)
      
      if (jsonObj.reply && jsonObj.display_type) {
         replyText = jsonObj.reply
         displayType = jsonObj.display_type
         if (jsonObj.display_type === 'tree') {
           parsedData = jsonObj.data
         } else if (jsonObj.data && Array.isArray(jsonObj.data)) {
           parsedData = jsonObj.data
         }
      }
    } catch (e) {
      // Keep as standard raw text
    }

    if (response.data.response) {
      messages.value.push({
        role: 'assistant',
        content: replyText,
        data: toolData,
        parsedData: parsedData,
        displayType: displayType
      })
    } else {
      messages.value.push({
        role: 'assistant',
        content: JSON.stringify(response.data, null, 2)
      })
    }
  } catch (error: any) {
    isTyping.value = false
    messages.value.push({
      role: 'error',
      content: `Erreur: ${error.response?.data?.detail || error.message}`
    })
  } finally {
    scrollToBottom()
  }
}

// Handle search query from URL or Events
const handleSearch = (queryText: string) => {
  if (!queryText) return
  sendQuery(`cherche l'utilisateur nommé ${queryText}`)
  // Clean URL to avoid re-triggering on refresh
  router.replace({ query: {} })
}

const handleSearchEvent = (event: any) => {
  handleSearch(event.detail)
}

onMounted(() => {
  window.addEventListener('search-user', handleSearchEvent)
  
  // Check for search query in URL on mount
  if (route.query.q) {
    handleSearch(route.query.q as string)
  }
})

// Also watch for query changes if already on Home page
watch(() => route.query.q, (newQ) => {
  if (newQ) {
    handleSearch(newQ as string)
  }
})

onUnmounted(() => {
  window.removeEventListener('search-user', handleSearchEvent)
})

const getInitials = (name: string) => {
  if (!name) return '?'
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

const goToUser = (id: number) => {
  router.push({ name: 'user-detail', params: { id: id.toString() } })
}
</script>

<template>
  <div class="chat-wrapper">
    <div class="chat-container" ref="chatContainer">
      <!-- Project Introduction -->
      <div class="welcome-section">
        <h2>Bienvenue sur l'Agent Zenika</h2>
        <p>
          Cette console est une plateforme d'expérimentation pour l'orchestration de microservices via des agents intelligents. 
          Grâce au protocole <strong>MCP (Model Context Protocol)</strong>, l'assistant Gemini peut interagir en temps réel avec nos APIs 
          pour gérer les profils utilisateurs, le catalogue d'objets et la cartographie des compétences.
        </p>
        <div class="quick-tips">
          <span>💡 Essayez : "Liste les items de Bob"</span>
          <span>💡 Essayez : "Quelles compétences a Alice ?"</span>
        </div>
      </div>

      <div v-for="(msg, index) in messages" :key="index" :class="['message', msg.role]">
        <div v-if="msg.role === 'assistant'" class="assistant-content">
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
                  <tr v-for="(row, idx) in msg.parsedData" :key="idx" @click="row.id || row.user_id ? goToUser(row.id || row.user_id) : null" :class="{ 'clickable-row': row.id || row.user_id }">
                    <td v-for="key in Object.keys(msg.parsedData[0]).filter(k => !k.startsWith('_'))" :key="key">{{ row[key] }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Generic Cards UI -->
            <div v-else-if="msg.displayType === 'cards'" class="generic-grid">
               <div v-for="(obj, idx) in msg.parsedData" :key="idx" class="generic-dash-card" @click="obj.id || obj.user_id ? goToUser(obj.id || obj.user_id) : null">
                  <div class="card-header" v-if="obj.username || obj.name || obj.full_name">
                    <h3 class="name">{{ obj.full_name || obj.username || obj.name }}</h3>
                    <div v-if="obj.id || obj.user_id" class="id-tag"><Hash size="12" />{{ obj.id || obj.user_id }}</div>
                  </div>
                  <div class="card-body">
                    <div v-for="key in Object.keys(obj).filter(k => !['id', 'user_id', 'username', 'name', 'full_name'].includes(k))" :key="key" class="data-row">
                      <strong>{{ key }}:</strong> <span>{{ obj[key] }}</span>
                    </div>
                  </div>
               </div>
            </div>

            <!-- Tree View UI -->
            <div v-else-if="msg.displayType === 'tree'" class="tree-grid">
               <div class="tree-header">
                 <Network size="20" class="tree-icon" /> 
                 <h3>Taxonomie RAG Modélisée</h3>
               </div>
               <div class="tree-content">
                  <pre class="json-viewer">{{ JSON.stringify(msg.parsedData, null, 2) }}</pre>
               </div>
            </div>
          </div>

          <!-- Legacy Tool Data Dashboard (Fallback) -->
          <div v-else-if="msg.data && msg.data.items" class="dashboard-content">
            <div v-if="msg.data.dataType === 'user'" class="user-grid">
              <div 
                v-for="user in msg.data.items" 
                :key="user.id" 
                class="user-dash-card clickable"
                @click="goToUser(user.id)"
              >
                <div class="card-header">
                  <div class="avatar">{{ getInitials(user.full_name || user.username) }}</div>
                  <div class="id-tag"><Hash size="12" />{{ user.id }}</div>
                </div>
                <div class="card-body">
                  <h3 class="name">{{ user.full_name || user.username }}</h3>
                  <div class="username">@{{ user.username }}</div>
                  <div class="email"><Mail size="14" /> {{ user.email }}</div>
                </div>
                <div class="card-footer">
                  <div :class="['status-pill', user.is_active ? 'active' : 'inactive']">
                    <CheckCircle2 v-if="user.is_active" size="14" />
                    <XCircle v-else size="14" />
                    {{ user.is_active ? 'Actif' : 'Inactif' }}
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Item Grid -->
            <div v-else-if="msg.data.dataType === 'item'" class="item-grid">
              <div v-for="item in msg.data.items" :key="item.id" class="item-dash-card">
                <div class="status-dot-glow"></div>
                <div class="item-icon-wrapper"><Package size="20" /></div>
                <div class="item-info">
                  <h4 class="name">{{ item.name }}</h4>
                  <p class="desc">{{ item.description }}</p>
                  <div class="owner">Propriétaire: #{{ item.user_id }}</div>
                  <div v-if="item.categories" class="categories-tags">
                    <span v-for="cat in item.categories" :key="cat.id" class="tag">
                      <Tag size="10" /> {{ cat.name }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <div v-else class="user-content">
          {{ msg.content }}
        </div>
      </div>
      
      <div v-if="isTyping" class="message assistant typing">
        <span></span><span></span><span></span>
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
        <button @click="sendQuery()" :disabled="isTyping">Envoyer</button>
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

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 2.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.welcome-section {
  background: linear-gradient(135deg, rgba(227, 25, 55, 0.03) 0%, rgba(255, 255, 255, 1) 100%);
  padding: 2rem;
  border-radius: 20px;
  border: 1px solid rgba(227, 25, 55, 0.1);
  margin-bottom: 2rem;
}

.welcome-section h2 {
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--zenika-red);
  margin-bottom: 1rem;
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

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
</style>
