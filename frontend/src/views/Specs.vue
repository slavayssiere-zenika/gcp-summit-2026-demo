<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import markdownit from 'markdown-it'
import { BookOpen, AlertCircle, RefreshCw, Cpu, Database, Network, KeyRound, FileText } from 'lucide-vue-next'

const md = markdownit({
  html: true,
  linkify: true,
  typographer: true
})

interface SpecTab {
  id: string
  name: string
  url: string
  icon: any
}

const tabs: SpecTab[] = [
  { id: 'agent', name: 'Agent API', url: '/api/spec', icon: Cpu },
  { id: 'users', name: 'Users API', url: '/users-api/spec', icon: KeyRound },
  { id: 'items', name: 'Items API', url: '/items-api/spec', icon: Database },
  { id: 'competencies', name: 'Competencies API', url: '/comp-api/spec', icon: Network },
  { id: 'cv', name: 'CV API', url: '/cv-api/spec', icon: FileText }
]

const activeTabId = ref(tabs[0].id)
const activeTab = computed(() => tabs.find(t => t.id === activeTabId.value) || tabs[0])

const content = ref('')
const loading = ref(false)
const error = ref('')

const fetchSpec = async () => {
  loading.value = true
  error.value = ''
  content.value = ''
  
  try {
    const response = await axios.get(activeTab.value.url)
    // The response is pure markdown text
    content.value = md.render(response.data)
  } catch (err: any) {
    error.value = `Indisponible : Impossible de contacter l'API ${activeTab.value.name}.`
    console.error(err)
  } finally {
    loading.value = false
  }
}

const selectTab = (id: string) => {
  activeTabId.value = id
  fetchSpec()
}

onMounted(() => {
  fetchSpec()
})
</script>

<template>
  <div class="specs-wrapper fade-in">
    <div class="header-section">
      <div class="title-wrapper">
        <BookOpen class="icon-title" size="32" />
        <h2>Specs & Manifestes API</h2>
      </div>
      <p class="subtitle">Architecture Documentaire des microservices Zenika</p>
    </div>

    <!-- Navigation Tab Bar -->
    <div class="tabs-container">
      <button 
        v-for="tab in tabs" 
        :key="tab.id"
        class="tab-btn"
        :class="{ active: activeTabId === tab.id }"
        @click="selectTab(tab.id)"
      >
        <component :is="tab.icon" size="18" class="tab-icon" />
        {{ tab.name }}
      </button>
    </div>

    <!-- Reader Interface -->
    <div class="reader-card glass-panel">
      <div class="card-header">
        <div class="card-title">
          <component :is="activeTab.icon" size="20" class="mini-icon" />
          <h3>Spécifications : {{ activeTab.name }}</h3>
        </div>
        <button class="icon-btn" @click="fetchSpec" :disabled="loading" title="Actualiser le manifeste">
          <RefreshCw size="18" :class="{ 'spin': loading }" />
        </button>
      </div>

      <div class="reader-body">
        <div v-if="loading" class="loading-state">
          <div class="spinner"></div>
          <span>Téléchargement des Blueprints...</span>
        </div>

        <div v-else-if="error" class="error-msg">
          <AlertCircle size="48" class="err-icon" />
          <p>{{ error }}</p>
          <button class="retry-btn" @click="fetchSpec">Réessayer</button>
        </div>

        <div v-else class="markdown-content" v-html="content"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.specs-wrapper {
  max-width: 1100px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header-section {
  text-align: center;
  margin-bottom: 30px;
}

.title-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 12px;
}

h2 {
  font-size: 36px;
  font-weight: 800;
  color: #fff;
  letter-spacing: -1px;
}

.icon-title {
  color: #E31937;
}

.subtitle {
  color: #888;
  font-size: 18px;
}

/* Tabs */
.tabs-container {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-bottom: 30px;
  flex-wrap: wrap;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  background: rgba(30, 30, 30, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  color: #aaa;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  backdrop-filter: blur(10px);
}

.tab-btn:hover {
  background: rgba(40, 40, 40, 0.8);
  color: #fff;
}

.tab-btn.active {
  background: #E31937;
  border-color: #ff3355;
  color: #fff;
  box-shadow: 0 4px 15px rgba(227, 25, 55, 0.3);
}

.tab-icon {
  opacity: 0.8;
}

.tab-btn.active .tab-icon {
  opacity: 1;
}

/* Glass Card */
.glass-panel {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 16px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 30px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  background: rgba(250, 250, 250, 0.9);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.mini-icon {
  color: #E31937;
}

h3 {
  font-size: 20px;
  font-weight: 700;
  color: #1A1A1A;
  margin: 0;
}

.icon-btn {
  background: transparent;
  border: 1px solid #ddd;
  color: #555;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.icon-btn:hover:not(:disabled) {
  background: #f0f0f0;
  color: #1A1A1A;
}

/* Reader Body */
.reader-body {
  padding: 40px;
  min-height: 400px;
}

.markdown-content {
  color: #1A1A1A;
  line-height: 1.6;
  font-size: 16px;
}

.markdown-content :deep(h1), .markdown-content :deep(h2), .markdown-content :deep(h3) {
  color: #111;
  margin-top: 1.5em;
  margin-bottom: 0.5em;
}

.markdown-content :deep(h1) {
  border-bottom: 2px solid rgba(227, 25, 55, 0.2);
  padding-bottom: 8px;
}

.markdown-content :deep(code) {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 14px;
  color: #d32f2f;
}

.markdown-content :deep(blockquote) {
  border-left: 4px solid #E31937;
  margin: 0;
  padding-left: 16px;
  color: #555;
  background: rgba(227, 25, 55, 0.02);
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
}

/* State UI */
.loading-state, .error-msg {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 60px 0;
  color: #555;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(227, 25, 55, 0.2);
  border-top-color: #E31937;
  border-radius: 50%;
  animation: spin 1s infinite linear;
  margin-bottom: 20px;
}

.spin {
  animation: spin 1s infinite linear;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.err-icon {
  color: #E31937;
  margin-bottom: 16px;
}

.retry-btn {
  margin-top: 20px;
  padding: 10px 24px;
  background: #E31937;
  color: #fff;
  border: none;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.retry-btn:hover {
  background: #c2132e;
}

.fade-in {
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
