<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import axios from 'axios'
import mermaid from 'mermaid'
import { Network, RefreshCw, AlertCircle, Info, Timer } from 'lucide-vue-next'

const loading = ref(true)
const error = ref<string | null>(null)
const topologyData = ref<any>(null)
const hoursLookback = ref(1)
const mermaidContainer = ref<HTMLElement | null>(null)

// Initialize Mermaid with Zenika colors and premium styling
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    primaryColor: '#E31937',
    primaryTextColor: '#fff',
    primaryBorderColor: '#E31937',
    lineColor: '#1A1A1A',
    secondaryColor: '#1A1A1A',
    tertiaryColor: '#fff',
    fontSize: '14px',
    fontFamily: 'Inter, sans-serif'
  },
  flowchart: {
    curve: 'basis',
    nodeSpacing: 50,
    rankSpacing: 80,
    htmlLabels: true
  }
})

const fetchTopology = async () => {
  loading.value = true
  error.value = null
  try {
    const token = localStorage.getItem('access_token')
    const response = await axios.get(`/monitoring-mcp/api/topology?hours_lookback=${hoursLookback.value}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    
    // The tool returns { result: "JSON_STRING" } or the object directly depending on format_mcp_result
    // But our direct endpoint should return the data part
    let rawData
    try {
      rawData = response.data.result ? JSON.parse(response.data.result) : response.data
    } catch (parseError) {
      console.error("Parse error:", parseError, response.data)
      error.value = "Format de réponse invalide. Détail technique : " + (response.data.result || response.data)
      return
    }

    // Check for backend-reported errors
    topologyData.value = rawData
    console.log("Topology Data Received:", topologyData.value)

    if (!topologyData.value?.nodes || topologyData.value.nodes.length === 0) {
      error.value = "Aucune trace détectée sur la période sélectionnée."
      loading.value = false
      return
    }

    loading.value = false
    await nextTick()
    await renderGraph()
  } catch (e: any) {
    console.error(e)
    error.value = "Impossible de récupérer la topologie. Vérifiez vos permissions GCP (Cloud Trace)."
    loading.value = false
  }
}

const renderGraph = async () => {
  if (!topologyData.value || !mermaidContainer.value) return

  // Build Mermaid Syntax
  let chart = 'graph TD\n'
  
  // Custom styles for Zenika services
  chart += '  classDef default fill:#fff,stroke:#e2e8f0,stroke-width:2px,color:#1e293b,rx:8,ry:8;\n'
  chart += '  classDef service fill:#E31937,stroke:#E31937,stroke-width:2px,color:#fff,rx:8,ry:8;\n'
  chart += '  classDef storage fill:#1A1A1A,stroke:#1A1A1A,stroke-width:2px,color:#fff,rx:8,ry:8;\n'
  chart += '  classDef lb fill:#0f172a,stroke:#0f172a,stroke-width:2px,color:#fff,rx:8,ry:8;\n'
  chart += '  classDef metadata fill:#64748b,stroke:#64748b,stroke-width:2px,color:#fff,rx:4,ry:4;\n'
  chart += '  classDef pubsub fill:#f59e0b,stroke:#f59e0b,stroke-width:2px,color:#fff,rx:8,ry:8;\n'
  chart += '  classDef user fill:#fff,stroke:#E31937,stroke-width:3px,color:#E31937,rx:20,ry:20;\n'


  const { nodes, links } = topologyData.value
  
  // Helper to sanitize IDs for Mermaid (Must start with letter, only alphanumeric and underscore)
  const sanitizeId = (id: string) => 'v_' + id.replace(/[^a-zA-Z0-9]/g, '_')

  nodes.forEach((node: any) => {
    const sId = sanitizeId(node.id)
    const label = node.label || node.id
    const type = node.type || 'service'

    if (type === 'alloydb' || type === 'redis' || type === 'database') {
       chart += `  ${sId}[("${label}")]\n`
       chart += `  class ${sId} storage\n`
    } else if (type === 'lb_public' || type === 'lb_private') {
       // Stadium shape for LB
       chart += `  ${sId}(["${label}"])\n`
       chart += `  class ${sId} lb\n`
    } else if (type === 'pubsub' || type === 'messaging') {
       // Subroutine shape for PubSub
       chart += `  ${sId}[["${label}"]]\n`
       chart += `  class ${sId} pubsub\n`
    } else if (type === 'user') {
       // Circle shape for User
       chart += `  ${sId}(("${label}"))\n`
       chart += `  class ${sId} user\n`
    } else if (type === 'metadata') {
       chart += `  ${sId}["${label}"]\n`
       chart += `  class ${sId} metadata\n`
    } else {
       chart += `  ${sId}["${label}"]\n`
       chart += `  class ${sId} service\n`
    }
  })

  links.forEach((link: any) => {
    chart += `  ${sanitizeId(link.source)} --> ${sanitizeId(link.target)}\n`
  })

  console.log("Generating Mermaid Chart:\n", chart)

  // Clear container
  if (mermaidContainer.value) mermaidContainer.value.innerHTML = ''
  
  await nextTick()
  try {
    // Generate a unique ID for each render to avoid Mermaid cache/DOM issues
    const renderId = `mermaid_render_${Date.now()}`
    const { svg } = await mermaid.render(renderId, chart)
    if (mermaidContainer.value) mermaidContainer.value.innerHTML = svg
  } catch (mermaidError: any) {
    console.error("Mermaid Render Error:", mermaidError)
    error.value = "Erreur de rendu graphique. Le schéma généré est invalide ou trop complexe."
    // Fallback: show the chart text for debugging if needed (optionally)
  }
}

onMounted(() => {
  fetchTopology()
})
</script>

<template>
  <div class="infra-view">
    <div class="view-header">
      <div class="title-group">
        <div class="icon-orb">
          <Network size="28" />
        </div>
        <div>
          <h1>Carte d'Infrastructure Dynamique</h1>
          <p>Visualisation en temps réel des dépendances via GCP Cloud Trace</p>
        </div>
      </div>
      
      <div class="actions">
        <div class="filter-group">
          <Timer size="16" />
          <select v-model="hoursLookback" @change="fetchTopology" class="zen-select">
            <option :value="1">Dernière heure</option>
            <option :value="4">4 Dernières heures</option>
            <option :value="24">Dernières 24 heures</option>
          </select>
        </div>
        <button @click="fetchTopology" class="refresh-btn" :disabled="loading">
          <RefreshCw size="18" :class="{ spin: loading }" />
          Rafraîchir
        </button>
      </div>
    </div>

    <div class="content-card">
      <div v-if="loading" class="loading-state">
        <div class="pulse-loader"></div>
        <p>Analyse des traces GCP en cours...</p>
      </div>

      <div v-else-if="error" class="error-state">
        <AlertCircle size="48" color="#E31937" />
        <h3>Oups !</h3>
        <p>{{ error }}</p>
        <div class="help-box">
          <Info size="16" />
          <p>Assurez-vous que le Service Account <strong>sa-market</strong> possède bien le rôle <strong>roles/cloudtrace.user</strong>.</p>
        </div>
        <button @click="fetchTopology" class="retry-btn">Réessayer</button>
      </div>

      <div v-else class="graph-container">
        <div v-if="topologyData?.links?.length === 0" class="link-hint">
          <Info size="16" />
          <p>Services détectés, mais aucun lien de communication capturé. (Vérifiez la propagation des traces ou attendez quelques minutes)</p>
        </div>
        
        <div ref="mermaidContainer" class="mermaid-output"></div>
        
        <div class="legend">
          <div class="legend-item">
            <span class="dot user"></span> Utilisateur
          </div>
          <div class="legend-item">
            <span class="dot zenika"></span> Service Backend
          </div>
          <div class="legend-item">
            <span class="dot lb"></span> Proxy & Ingress
          </div>
          <div class="legend-item">
            <span class="dot storage"></span> Base & Cache
          </div>
          <div class="legend-item">
            <span class="dot metadata"></span> GCP & Externe
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.infra-view {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  animation: fadeIn 0.5s ease-out;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title-group {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.icon-orb {
  background: var(--zenika-red);
  color: white;
  padding: 1rem;
  border-radius: 16px;
  box-shadow: 0 8px 16px rgba(227, 25, 55, 0.2);
}

.title-group h1 {
  font-size: 1.8rem;
  font-weight: 800;
  letter-spacing: -0.5px;
  margin-bottom: 0.25rem;
}

.title-group p {
  color: var(--text-light);
  font-size: 1rem;
}

.actions {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.zen-select {
  background: white;
  border: 1px solid var(--border-color);
  padding: 0.6rem 2.5rem 0.6rem 1rem;
  border-radius: 12px;
  font-weight: 600;
  color: var(--text-color);
  appearance: none;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-group {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-light);
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: var(--surface-light);
  border: 1px solid var(--border-color);
  padding: 0.6rem 1.25rem;
  border-radius: 12px;
  font-weight: 700;
  color: var(--text-color);
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  border-color: var(--zenika-red);
  color: var(--zenika-red);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.content-card {
  background: white;
  border-radius: 24px;
  border: 1px solid rgba(0,0,0,0.05);
  box-shadow: 0 10px 40px rgba(0,0,0,0.04);
  min-height: 600px;
  padding: 2rem;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
  overflow: hidden;
}

.graph-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
}

.link-hint {
  background: #f0f9ff;
  color: #0369a1;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.9rem;
  border: 1px solid #bae6fd;
}

.mermaid-output {
  flex: 1;
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

/* Custom styling for Mermaid SVG */
:deep(svg) {
  max-width: 100%;
  max-height: 500px;
  width: auto;
  height: auto;
}

/* Custom styling for Mermaid SVG */
:deep(svg) {
  max-width: 100%;
  height: auto;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
  color: var(--text-light);
}

.pulse-loader {
  width: 60px;
  height: 60px;
  background: var(--zenika-red);
  border-radius: 50%;
  animation: pulse 1.5s infinite ease-out;
}

@keyframes pulse {
  0% { transform: scale(0.8); opacity: 0.8; box-shadow: 0 0 0 0 rgba(227, 25, 55, 0.4); }
  70% { transform: scale(1); opacity: 0.3; box-shadow: 0 0 0 20px rgba(227, 25, 55, 0); }
  100% { transform: scale(0.8); opacity: 0.8; }
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 1rem;
  max-width: 450px;
}

.error-state h3 {
  font-size: 1.5rem;
  font-weight: 800;
}

.help-box {
  background: #fff5f5;
  border-radius: 12px;
  padding: 1rem;
  margin: 1rem 0;
  display: flex;
  gap: 0.75rem;
  font-size: 0.9rem;
  color: #c53030;
  text-align: left;
  border: 1px solid rgba(227, 25, 55, 0.1);
}

.retry-btn {
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 0.75rem 2rem;
  border-radius: 12px;
  font-weight: 700;
  cursor: pointer;
}

.legend {
  display: flex;
  gap: 2rem;
  background: #f8fafc;
  padding: 0.75rem 2rem;
  border-radius: 30px;
  border: 1px solid #e2e8f0;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-light);
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}

.dot.zenika { background: var(--zenika-red); }
.dot.user { border: 2px solid var(--zenika-red); background: white; border-radius: 50%; }
.dot.storage { background: #1A1A1A; }
.dot.lb { background: #0f172a; }
.dot.metadata { background: #64748b; }
.dot.default { background: #fff; border: 2px solid #e2e8f0; }

.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>
