<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import { 
  BarChart, 
  TrendingUp, 
  Users, 
  DollarSign, 
  Calendar, 
  RefreshCw, 
  AlertCircle,
  Database,
  ArrowUpRight,
  ArrowDownRight,
  Zap,
  Cpu,
  Table
} from 'lucide-vue-next'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
  Filler
} from 'chart.js'
import { Line, Doughnut } from 'vue-chartjs'

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
  Filler
)

interface MetricData {
  monthly: Array<{ month: string, cost: number, requests: number }>
  daily: Array<{ day: string, cost: number, requests: number }>
  top_users_count: Array<{ user_email: string, count: number }>
  top_users_cost: Array<{ user_email: string, cost: number }>
  top_actions: Array<{ action: string, count: number }>
  top_models: Array<{ model: string, count: number }>
  pricing_table: Array<{ model_name: string, input_cost_per_token: number, output_cost_per_token: number }>
  generated_at: string
}

const data = ref<MetricData | null>(null)
const loading = ref(true)
const error = ref('')

const fetchMetrics = async (force: boolean = false) => {
  loading.value = true
  error.value = ''
  try {
    const url = force ? '/api/analytics/metrics/aiops?force=true' : '/api/analytics/metrics/aiops'
    const res = await axios.get(url)
    data.value = res.data
  } catch (err: any) {
    error.value = "Impossible de charger les données AIOps. Vérifiez votre connexion."
    console.error(err)
  } finally {
    loading.value = false
  }
}

onMounted(() => fetchMetrics(false))

// KPI Calculations
const currentMonth = computed(() => data.value?.monthly[0] || { cost: 0, requests: 0 })
const lastMonth = computed(() => data.value?.monthly[1] || { cost: 0, requests: 0 })

const costTrend = computed(() => {
  if (!currentMonth.value.cost || !lastMonth.value.cost) return 0
  return ((currentMonth.value.cost - lastMonth.value.cost) / lastMonth.value.cost) * 100
})

// Chart Configurations
const lineChartData = computed(() => {
  if (!data.value) return { labels: [], datasets: [] }
  return {
    labels: data.value.daily.map(d => new Date(d.day).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })),
    datasets: [
      {
        label: 'Coût ($)',
        data: data.value.daily.map(d => d.cost),
        borderColor: '#E31937',
        backgroundColor: 'rgba(227, 25, 55, 0.1)',
        fill: true,
        tension: 0.4,
        yAxisID: 'y',
      },
      {
        label: 'Requêtes',
        data: data.value.daily.map(d => d.requests),
        borderColor: '#1A1A1A',
        backgroundColor: 'transparent',
        borderDash: [5, 5],
        tension: 0.4,
        yAxisID: 'y1',
      }
    ]
  }
})

const lineChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: {
    mode: 'index' as const,
    intersect: false,
  },
  scales: {
    y: {
      type: 'linear' as const,
      display: true,
      position: 'left' as const,
      title: { display: true, text: 'Coût USD' }
    },
    y1: {
      type: 'linear' as const,
      display: true,
      position: 'right' as const,
      grid: { drawOnChartArea: false },
      title: { display: true, text: 'Nombre de requêtes' }
    }
  },
  plugins: {
    legend: { position: 'top' as const }
  }
}

const topCountChartData = computed(() => {
  if (!data.value) return { labels: [], datasets: [] }
  return {
    labels: data.value.top_users_count.map(u => u.user_email.split('@')[0]),
    datasets: [{
      data: data.value.top_users_count.map(u => u.count),
      backgroundColor: [
        '#E31937', '#1A1A1A', '#4A5568', '#718096', '#A0AEC0',
        '#CBD5E0', '#E2E8F0', '#EDF2F7', '#F7FAFC', '#FFFFFF'
      ]
    }]
  }
})

const topCostChartData = computed(() => {
  if (!data.value) return { labels: [], datasets: [] }
  return {
    labels: data.value.top_users_cost.map(u => u.user_email.split('@')[0]),
    datasets: [{
      data: data.value.top_users_cost.map(u => u.cost),
      backgroundColor: [
        '#E31937', '#FF4D6D', '#FF758F', '#FF8FA3', '#FFB3C1',
        '#1A1A1A', '#333333', '#4D4D4D', '#666666', '#808080'
      ]
    }]
  }
})

const topActionsChartData = computed(() => {
  if (!data.value) return { labels: [], datasets: [] }
  return {
    labels: data.value.top_actions.map(a => a.action),
    datasets: [{
      data: data.value.top_actions.map(a => a.count),
      backgroundColor: [
        '#E31937', '#FF4D6D', '#FF758F', '#FF8FA3', '#FFB3C1',
        '#1A1A1A', '#333333', '#4D4D4D', '#666666', '#808080',
        '#A0AEC0', '#CBD5E0', '#E2E8F0', '#4A9EFF', '#1A73E8'
      ],
      borderWidth: 2,
      borderColor: 'rgba(255,255,255,0.8)'
    }]
  }
})

const topModelsChartData = computed(() => {
  if (!data.value) return { labels: [], datasets: [] }
  return {
    labels: data.value.top_models.map(m => m.model),
    datasets: [{
      data: data.value.top_models.map(m => m.count),
      backgroundColor: [
        '#7C3AED', '#9D5CE8', '#B983F4', '#D0A8F9', '#E8CFF9',
        '#2563EB', '#3B82F6', '#60A5FA', '#93C5FD', '#BFDBFE'
      ],
      borderWidth: 2,
      borderColor: 'rgba(255,255,255,0.8)'
    }]
  }
})

const doughnutOptionsCompact = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'right' as const,
      labels: { boxWidth: 10, font: { size: 9 }, padding: 6 }
    },
    tooltip: {
      callbacks: {
        label: (ctx: any) => ` ${ctx.label}: ${ctx.parsed} appels`
      }
    }
  }
}

const doughnutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'right' as const,
      labels: { boxWidth: 12, font: { size: 10 } }
    }
  }
}
</script>

<template>
  <div class="aiops-container fade-in">
    <div class="header-section">
      <div class="title-wrapper">
        <BarChart class="icon-title" size="32" />
        <h2>Observabilité AIOps</h2>
        <button @click="fetchMetrics(true)" class="refresh-btn" :disabled="loading" title="Rafraîchir le cache">
          <RefreshCw :class="{ 'spinning': loading }" size="20" />
        </button>
      </div>
      <p class="subtitle">Suivi de la consommation et des coûts liés à l'Intelligence Artificielle</p>
    </div>

    <div v-if="loading" class="loading-overlay">
      <div class="spinner"></div>
      <span>Calcul des indicateurs FinOps...</span>
    </div>

    <div v-else-if="error" class="error-card glass-panel">
      <AlertCircle size="48" color="#E31937" />
      <h3>Erreur de chargement</h3>
      <p>{{ error }}</p>
      <button @click="fetchMetrics" class="retry-btn">Réessayer</button>
    </div>

    <div v-else class="dashboard-grid">
      <!-- KPI Row -->
      <div class="kpi-row">
        <div class="kpi-card glass-panel">
          <div class="kpi-icon cost"><DollarSign size="20" /></div>
          <div class="kpi-content">
            <span class="kpi-label">Ce Mois</span>
            <span class="kpi-value">${{ currentMonth.cost.toFixed(2) }}</span>
            <div class="kpi-trend" :class="costTrend > 0 ? 'up' : 'down'">
              <component :is="costTrend > 0 ? ArrowUpRight : ArrowDownRight" size="14" />
              {{ Math.abs(costTrend).toFixed(1) }}% vs mois dernier
            </div>
          </div>
        </div>

        <div class="kpi-card glass-panel">
          <div class="kpi-icon requests"><Database size="20" /></div>
          <div class="kpi-content">
            <span class="kpi-label">Requêtes (Mois)</span>
            <span class="kpi-value">{{ currentMonth.requests }}</span>
            <span class="kpi-subtext">Usage global agent & outils</span>
          </div>
        </div>

        <div class="kpi-card glass-panel">
          <div class="kpi-icon history"><Calendar size="20" /></div>
          <div class="kpi-content">
            <span class="kpi-label">Mois Dernier</span>
            <span class="kpi-value">${{ lastMonth.cost.toFixed(2) }}</span>
            <span class="kpi-subtext">{{ lastMonth.requests }} requêtes traitées</span>
          </div>
        </div>
      </div>

      <!-- Main Evolution Chart -->
      <div class="chart-card glass-panel main-chart">
        <div class="chart-header">
          <h3>Évolution Quotidienne (30 jours)</h3>
          <TrendingUp size="18" class="text-secondary" />
        </div>
        <div class="chart-body">
          <Line :data="lineChartData" :options="lineChartOptions" />
        </div>
      </div>

      <!-- Top Users Section -->
      <div class="charts-row">
        <div class="chart-card glass-panel flex-1">
          <div class="chart-header">
            <h3>Top 10 Requéteurs (Volume)</h3>
            <Users size="18" class="text-secondary" />
          </div>
          <div class="chart-body doughnut">
            <Doughnut :data="topCountChartData" :options="doughnutOptions" />
          </div>
        </div>

        <div class="chart-card glass-panel flex-1">
          <div class="chart-header">
            <h3>Top 10 Requéteurs (Coût)</h3>
            <DollarSign size="18" class="text-secondary" />
          </div>
          <div class="chart-body doughnut">
            <Doughnut :data="topCostChartData" :options="doughnutOptions" />
          </div>
        </div>
      </div>

      <!-- Actions & Models Distribution -->
      <div class="section-divider">
        <span class="section-label">Répartition par Usage</span>
      </div>

      <div class="charts-row">
        <div class="chart-card glass-panel flex-1">
          <div class="chart-header">
            <h3>Actions LLM (Top 15)</h3>
            <Zap size="18" class="text-accent" />
          </div>
          <p class="chart-subtitle">Distribution des outils et actions appelés par les agents</p>
          <div class="chart-body doughnut-lg">
            <Doughnut :data="topActionsChartData" :options="doughnutOptionsCompact" />
          </div>
        </div>

        <div class="chart-card glass-panel flex-1">
          <div class="chart-header">
            <h3>Modèles IA (Top 10)</h3>
            <Cpu size="18" class="text-purple" />
          </div>
          <p class="chart-subtitle">Répartition des requêtes par modèle Gemini utilisé</p>
          <div class="chart-body doughnut-lg">
            <Doughnut :data="topModelsChartData" :options="doughnutOptionsCompact" />
          </div>
        </div>
      </div>
      
      <!-- Table des Prix (Reference) -->
      <div class="section-divider">
        <span class="section-label">Référentiel des Coûts</span>
      </div>
      
      <div class="pricing-card glass-panel">
        <div class="chart-header">
          <h3>Tarification des Modèles</h3>
          <Table size="18" class="text-secondary" />
        </div>
        <p class="chart-subtitle" style="margin-top: 8px;">Coûts unitaires par Token (USD) pour les modèles Gemini enregistrés.</p>
        <div class="table-container">
          <table class="pricing-table">
            <thead>
              <tr>
                <th>Modèle API</th>
                <th>Coût Entrée (1M Tokens)</th>
                <th>Coût Sortie (1M Tokens)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="price in data?.pricing_table || []" :key="price.model_name">
                <td class="model-name-cell"><div class="model-badge">{{ price.model_name }}</div></td>
                <td>${{ (price.input_cost_per_token * 1000000).toFixed(2) }}</td>
                <td>${{ (price.output_cost_per_token * 1000000).toFixed(2) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="footer-info">
        <RefreshCw size="14" />
        Dernière mise à jour : {{ new Date(data.generated_at).toLocaleString() }} | Données rafraîchies toutes les heures.
      </div>
    </div>
  </div>
</template>

<style scoped>
.aiops-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header-section {
  text-align: center;
  margin-bottom: 40px;
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
  color: #1A1A1A;
  letter-spacing: -1px;
}

.refresh-btn {
  background: transparent;
  border: none;
  color: #718096;
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  margin-left: 8px;
}
.refresh-btn:hover:not(:disabled) {
  background: rgba(113, 128, 150, 0.1);
  color: #1A1A1A;
}
.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.spinning {
  animation: spin 1s linear infinite;
}

.icon-title {
  color: #E31937;
}

.subtitle {
  color: #666;
  font-size: 18px;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 20px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.03);
}

.dashboard-grid {
  display: flex;
  flex-direction: column;
  gap: 30px;
}

/* KPI Cards */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

.kpi-card {
  display: flex;
  padding: 24px;
  gap: 20px;
  align-items: center;
}

.kpi-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.kpi-icon.cost { background: rgba(227, 25, 55, 0.1); color: #E31937; }
.kpi-icon.requests { background: rgba(26, 32, 44, 0.1); color: #1A1A1A; }
.kpi-icon.history { background: rgba(74, 85, 104, 0.1); color: #4A5568; }

.kpi-content {
  display: flex;
  flex-direction: column;
}

.kpi-label {
  font-size: 13px;
  font-weight: 600;
  color: #718096;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.kpi-value {
  font-size: 28px;
  font-weight: 800;
  color: #1A1A1A;
  margin: 4px 0;
}

.kpi-trend {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
}

.kpi-trend.up { color: #E31937; }
.kpi-trend.down { color: #38A169; }

.kpi-subtext {
  font-size: 13px;
  color: #A0AEC0;
}

/* Charts */
.chart-card {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-header h3 {
  font-size: 18px;
  font-weight: 700;
}

.chart-body {
  height: 350px;
  position: relative;
}

.chart-body.doughnut {
  height: 250px;
}

.chart-body.doughnut-lg {
  height: 300px;
}

.chart-subtitle {
  font-size: 12px;
  color: #A0AEC0;
  margin: -12px 0 0;
}

.charts-row {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.flex-1 { flex: 1; min-width: 400px; }

/* Section divider */
.section-divider {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 8px 0;
}

.section-divider::before,
.section-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(to right, transparent, #E2E8F0, transparent);
}

.section-label {
  font-size: 11px;
  font-weight: 700;
  color: #A0AEC0;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  white-space: nowrap;
  padding: 0 8px;
}

/* Icon color variants */
.text-accent { color: #E31937; }
.text-purple { color: #7C3AED; }

.footer-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #A0AEC0;
  font-size: 12px;
  margin-top: 20px;
}

/* Loading & Error */
.loading-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  padding: 100px 0;
}

.spinner {
  width: 50px;
  height: 50px;
  border: 4px solid rgba(227, 25, 55, 0.1);
  border-top-color: #E31937;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.error-card {
  padding: 60px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.retry-btn {
  padding: 12px 30px;
  background: #E31937;
  color: white;
  border: none;
  border-radius: 10px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
}

.retry-btn:hover { background: #c2132e; transform: scale(1.05); }

.fade-in { animation: fadeIn 0.5s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.text-secondary { color: #718096; }

/* Pricing Table */
.pricing-card {
  padding: 24px;
}

.table-container {
  margin-top: 16px;
  overflow-x: auto;
}

.pricing-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 14px;
}

.pricing-table th {
  padding: 12px 16px;
  color: #718096;
  font-weight: 600;
  border-bottom: 1px solid #E2E8F0;
  white-space: nowrap;
}

.pricing-table td {
  padding: 12px 16px;
  color: #1A1A1A;
  border-bottom: 1px solid rgba(226, 232, 240, 0.5);
  font-weight: 500;
}

.pricing-table tbody tr:hover {
  background: rgba(247, 250, 252, 0.5);
}

.model-name-cell {
  width: 50%;
}

.model-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  background: rgba(124, 58, 237, 0.1);
  color: #7C3AED;
  border-radius: 6px;
  font-family: monospace;
  font-weight: 600;
  font-size: 13px;
}
</style>
