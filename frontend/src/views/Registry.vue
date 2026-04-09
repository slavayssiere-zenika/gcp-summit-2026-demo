<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { Terminal, Database, Cpu, ChevronRight, Activity, Code2, Box, Cloud } from 'lucide-vue-next'

interface Parameter {
  name: string
  type: string
  default: string | null
  required: boolean
}

interface Tool {
  name: string
  description: string
  parameters: Parameter[]
}

interface Service {
  id: string
  name: string
  tools: Tool[]
}

const services = ref<Service[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const selectedService = ref<string | null>(null)

const fetchRegistry = async () => {
  try {
    const response = await axios.get('/api/mcp/registry')
    services.value = response.data.services
    if (services.value.length > 0) {
      selectedService.value = services.value[0].id
    }
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || 'Erreur lors du chargement du registre'
  } finally {
    loading.value = false
  }
}

onMounted(fetchRegistry)

const currentService = () => services.value.find(s => s.id === selectedService.value)
</script>

<template>
  <div class="registry-container">
    <header class="registry-header">
      <div class="title-group">
        <h1>MCP Technical Registry</h1>
        <p>Vue consolidée des descripteurs techniques de tous les microservices intégrés.</p>
      </div>
      <div class="stats-bar">
        <div class="stat-item">
          <Activity size="18" />
          <span>{{ services.length }} Services</span>
        </div>
        <div class="stat-item">
          <Code2 size="18" />
          <span>{{ services.reduce((acc, s) => acc + s.tools.length, 0) }} Tools</span>
        </div>
      </div>
    </header>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      Chargement du registre technique...
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button @click="fetchRegistry">Réessayer</button>
    </div>

    <div v-else class="registry-layout">
      <!-- Sidebar Navigation -->
      <aside class="registry-sidebar">
        <div 
          v-for="service in services" 
          :key="service.id"
          :class="['service-nav-item', { active: selectedService === service.id }]"
          @click="selectedService = service.id"
        >
          <div class="nav-icon">
            <Database v-if="service.id === 'users'" />
            <Box v-else-if="service.id === 'items'" />
            <Cloud v-else-if="service.id === 'drive'" />
            <Cpu v-else />
          </div>
          <div class="nav-info">
            <span class="nav-name">{{ service.name }}</span>
            <span class="nav-count">{{ service.tools.length }} endpoints</span>
          </div>
          <ChevronRight class="nav-arrow" size="16" />
        </div>
      </aside>

      <!-- Main Content -->
      <main v-if="currentService()" class="registry-main">
        <div class="tools-grid">
          <div v-for="tool in currentService()?.tools" :key="tool.name" class="tool-card">
            <div class="tool-card-header">
              <div class="tool-type-icon">
                <Terminal size="16" />
              </div>
              <h3>{{ tool.name }}</h3>
            </div>
            
            <p class="tool-desc">{{ tool.description }}</p>

            <div class="params-section">
              <div class="params-header">Descripteur d'arguments :</div>
              <div class="params-table">
                <div class="param-row header">
                  <span>Nom</span>
                  <span>Type</span>
                  <span>Requis</span>
                  <span>Défaut</span>
                </div>
                <div v-for="param in tool.parameters" :key="param.name" class="param-row">
                  <span class="code-text">{{ param.name }}</span>
                  <span class="type-text">{{ param.type }}</span>
                  <span class="status-cell">
                    <span v-if="param.required" class="required-badge">Yes</span>
                    <span v-else class="optional-badge">No</span>
                  </span>
                  <span class="code-text dimmed">{{ param.default || '-' }}</span>
                </div>
              </div>
            </div>

            <div class="technical-snippet">
              <div class="snippet-header">JSON Spec</div>
              <pre><code>{
  "method": "{{ tool.name }}",
  "params": {
    {{ tool.parameters.map(p => `"${p.name}": "${p.type}"`).join(',\n    ') }}
  }
}</code></pre>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.registry-container {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.registry-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  background: white;
  padding: 2.5rem;
  border-radius: 24px;
  box-shadow: var(--shadow-sm);
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.title-group h1 {
  font-size: 2.4rem;
  font-weight: 800;
  color: var(--zenika-red);
  letter-spacing: -1.5px;
  margin-bottom: 0.5rem;
}

.title-group p {
  color: var(--text-secondary);
  font-size: 1.1rem;
}

.stats-bar {
  display: flex;
  gap: 1.5rem;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #f8f9fa;
  padding: 0.6rem 1rem;
  border-radius: 12px;
  font-size: 0.9rem;
  font-weight: 600;
  color: #555;
  border: 1px solid #eee;
}

.registry-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 2rem;
  align-items: start;
}

/* Sidebar Styling */
.registry-sidebar {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  background: white;
  padding: 1rem;
  border-radius: 24px;
  box-shadow: var(--shadow-sm);
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.service-nav-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.service-nav-item:hover {
  background: #f8f9fa;
  transform: translateX(4px);
}

.service-nav-item.active {
  background: rgba(227, 25, 55, 0.05);
  border-color: rgba(227, 25, 55, 0.2);
  color: var(--zenika-red);
}

.nav-icon {
  background: #f1f3f5;
  padding: 0.75rem;
  border-radius: 12px;
  display: flex;
  color: #666;
}

.active .nav-icon {
  background: var(--zenika-red);
  color: white;
}

.nav-info {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.nav-name {
  font-weight: 700;
  font-size: 0.95rem;
}

.nav-count {
  font-size: 0.75rem;
  opacity: 0.7;
  font-weight: 500;
}

.nav-arrow {
  opacity: 0.3;
}

/* Main Content Styling */
.registry-main {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.tools-grid {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.tool-card {
  background: white;
  padding: 2rem;
  border-radius: 24px;
  box-shadow: var(--shadow-sm);
  border: 1px solid rgba(0, 0, 0, 0.03);
}

.tool-card-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.tool-type-icon {
  background: #1a1a1a;
  color: white;
  padding: 0.5rem;
  border-radius: 8px;
  display: flex;
}

.tool-card-header h3 {
  font-size: 1.25rem;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.tool-desc {
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 2rem;
}

.params-section {
  margin-bottom: 1.5rem;
}

.params-header {
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  color: #999;
  letter-spacing: 0.5px;
  margin-bottom: 0.75rem;
}

.params-table {
  border: 1px solid #eee;
  border-radius: 12px;
  overflow: hidden;
}

.param-row {
  display: grid;
  grid-template-columns: 1fr 1fr 100px 1fr;
  padding: 0.75rem 1.25rem;
  font-size: 0.9rem;
  background: white;
  align-items: center;
}

.param-row.header {
  background: #f8f9fa;
  font-weight: 700;
  font-size: 0.75rem;
  color: #666;
  text-transform: uppercase;
}

.param-row:not(:last-child) {
  border-bottom: 1px solid #f1f3f5;
}

.code-text {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  font-size: 0.85rem;
}

.type-text {
  color: var(--zenika-red);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
}

.dimmed {
  opacity: 0.4;
}

.required-badge {
  background: #fff0f0;
  color: #e31937;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 800;
}

.optional-badge {
  background: #f1f3f5;
  color: #666;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 700;
}

.technical-snippet {
  margin-top: 2rem;
  background: #1a1a1a;
  border-radius: 16px;
  overflow: hidden;
}

.snippet-header {
  background: #2a2a2a;
  padding: 0.5rem 1.25rem;
  font-size: 0.7rem;
  font-weight: 700;
  color: #999;
  text-transform: uppercase;
}

pre {
  padding: 1.25rem;
  margin: 0;
  color: #f8f8f2;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  line-height: 1.5;
}

/* Common UI */
.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(227, 25, 55, 0.1);
  border-left-color: var(--zenika-red);
  border-radius: 50%;
  animation: rotate 1s linear infinite;
}

@keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.loading-state, .error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1.5rem;
  padding: 4rem;
  background: white;
  border-radius: 24px;
}
</style>
