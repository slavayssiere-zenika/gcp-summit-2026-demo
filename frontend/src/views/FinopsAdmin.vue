<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { ShieldAlert, PlayCircle, Loader2, CheckCircle, Database } from 'lucide-vue-next'

const isAnalyzing = ref(false)
const results = ref<any>(null)
const errorMsg = ref('')

const runAnalysis = async () => {
  isAnalyzing.value = true
  results.value = null
  errorMsg.value = ''
  
  try {
    const token = localStorage.getItem('access_token')
    // Le call proxy HTTP va pointer sur Market MCP -> /api/admin/finops/detect
    const response = await axios.post('/api/mcp/proxy/market_mcp/api/admin/finops/detect', {}, {
      headers: { Authorization: `Bearer ${token}` }
    })
    results.value = response.data
  } catch (e: any) {
    console.error(e)
    errorMsg.value = e.response?.data?.detail || e.message || 'Une erreur est survenue'
  } finally {
    isAnalyzing.value = false
  }
}
</script>

<template>
  <div class="finops-admin-page">
    <div class="header">
      <div class="title-wrap">
        <ShieldAlert size="28" style="color: var(--zenika-red);" />
        <h1>Anomaly Detection FinOps</h1>
      </div>
      <p>Protection contre l'Exfiltration de Connaissances et l'Epuisement Financier (Denial of Wallet).</p>
    </div>

    <div class="action-card">
      <div class="card-info">
        <h3>Scanner Manuel (Kill-Switch)</h3>
        <p>Le Job Cloud Scheduler exécute cette analyse automatiquement toutes les 15 minutes. Vous pouvez la lancer manuellement ci-dessous.</p>
      </div>
      
      <button class="run-btn" @click="runAnalysis" :disabled="isAnalyzing">
        <Loader2 v-if="isAnalyzing" size="20" class="spin" />
        <PlayCircle v-else size="20" />
        {{ isAnalyzing ? 'Analyse en cours...' : 'Lancer le diagnostic FinOps' }}
      </button>
    </div>

    <!-- Error State -->
    <div v-if="errorMsg" class="error-banner">
      <ShieldAlert size="20" />
      <span>{{ errorMsg }}</span>
    </div>

    <!-- Results State -->
    <div v-if="results" class="results-container">
      <div class="summary-stats">
        <div class="stat-box">
          <span class="label">Seuil Paramétré</span>
          <span class="val"><Database size="16" /> {{ results.threshold.toLocaleString() }} tokens / 15m</span>
        </div>
        <div class="stat-box" :class="results.anomalies_detected > 0 ? 'danger' : 'safe'">
          <span class="label">Anomalies Détectées</span>
          <span class="val">{{ results.anomalies_detected }}</span>
        </div>
      </div>

      <div class="details-section" v-if="results.details && results.details.length > 0">
        <h3>Comptes Suspendus</h3>
        <table class="zen-table">
          <thead>
            <tr>
              <th>Utilisateur (Email)</th>
              <th>Consommation / 15m</th>
              <th>Statut d'Intervention</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in results.details" :key="user.email">
              <td><strong>{{ user.email }}</strong></td>
              <td class="high-tokens">{{ user.tokens.toLocaleString() }}</td>
              <td>
                <span class="status-pill" :class="user.status === 'suspended' ? 'active' : 'inactive'">
                   <CheckCircle v-if="user.status === 'suspended'" size="14" />
                   {{ user.status === 'suspended' ? 'Banni avec succès' : 'Echec' }}
                </span>
                <span v-if="user.message" class="error-txt">{{ user.message }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <div v-else class="all-clear">
        <CheckCircle size="40" style="color: #10b981; margin-bottom: 1rem;" />
        <h3>Aucune anomalie détectée sur les 15 dernières minutes.</h3>
        <p>Vos systèmes sont sécures et l'usage reste dans les clous.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.finops-admin-page {
  padding: 2rem;
  max-width: 900px;
  margin: 0 auto;
}

.header {
  margin-bottom: 2rem;
}

.title-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.header h1 {
  font-size: 1.8rem;
  color: #1e293b;
}

.header p {
  color: #64748b;
  font-size: 1.05rem;
}

.action-card {
  background: white;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.05);
  border: 1px solid #edf2f7;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.card-info h3 {
  font-size: 1.2rem;
  color: #334155;
  margin-bottom: 0.5rem;
}

.card-info p {
  color: #64748b;
  font-size: 0.95rem;
}

.run-btn {
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 0.8rem 1.5rem;
  border-radius: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.2);
}

.run-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(227, 25, 55, 0.3);
}

.run-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin { 100% { transform: rotate(360deg); } }

.error-banner {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  padding: 1rem;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 2rem;
}

.results-container {
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.summary-stats {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-box {
  flex: 1;
  background: white;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.05);
  border: 1px solid #edf2f7;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stat-box.danger { border-color: #ef4444; border-left: 4px solid #ef4444; }
.stat-box.safe { border-left: 4px solid #10b981; }

.stat-box .label {
  color: #64748b;
  font-size: 0.9rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-box .val {
  font-size: 1.8rem;
  font-weight: 800;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-box.danger .val { color: #ef4444; }

.details-section h3 {
  margin-bottom: 1rem;
  color: #334155;
}

.zen-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 15px rgba(0,0,0,0.05);
}

.zen-table th, .zen-table td {
  padding: 1rem;
  text-align: left;
  border-bottom: 1px solid #edf2f7;
}

.zen-table th {
  background: #f8fafc;
  font-weight: 600;
  color: #475569;
}

.high-tokens {
  color: #ef4444;
  font-weight: 700;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.8rem;
  font-weight: 600;
}

.status-pill.active {
  background: #d1fae5;
  color: #065f46;
}

.status-pill.inactive {
  background: #fee2e2;
  color: #991b1b;
}

.error-txt {
  font-size: 0.8rem;
  color: #ef4444;
  margin-left: 10px;
}

.all-clear {
  background: white;
  border-radius: 16px;
  padding: 3rem;
  text-align: center;
  border: 1px solid #edf2f7;
  margin-top: 2rem;
}

.all-clear h3 { color: #334155; margin-bottom: 0.5rem; }
.all-clear p { color: #64748b; }
</style>
