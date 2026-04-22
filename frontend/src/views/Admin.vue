<script setup lang="ts">
import { ref } from 'vue'
import { Settings, ShieldCheck, BrainCircuit } from 'lucide-vue-next'
import { authService } from '../services/auth'
import DriveAdminPanel from '../components/DriveAdminPanel.vue'
import CVImportMonitor from '../components/CVImportMonitor.vue'

const error = ref('')
</script>

<template>
  <div class="admin-wrapper fade-in">
    <div class="header-banner">
      <div class="banner-icon"><Settings size="32" /></div>
      <div class="banner-text">
        <h2>Centre d'Administration Sécurisé</h2>
        <p>Espace réservé aux opérateurs système pour piloter les fonctions liées au stockage Drive et à l'ingestion IA.</p>
      </div>
      <div class="status-badge" v-if="authService.state.user?.role === 'admin'">
        <ShieldCheck size="16" /> Rôle Vérifié
      </div>
    </div>

    <div class="dashboard-grid">
      <!-- Moniteur d'analyses CV — temps réel -->
      <div class="full-width">
        <CVImportMonitor />
      </div>

      <!-- Administration des Prompts -->
      <div class="full-width">
        <div class="admin-panel" @click="$router.push('/admin/prompts')" style="cursor: pointer;">
          <div class="panel-header">
            <h3><BrainCircuit class="icon" /> Instructions IA & Auto-Correction</h3>
            <span class="status-badge pulse">Actif</span>
          </div>
          <div class="panel-content">
            <p>Pilotez les System Prompts dynamiques des agents et consultez le backlog d'Auto-Correction généré par détection d'erreurs.</p>
            <button class="action-btn primary-btn" style="margin-top: 15px;">
              Gérer les Instructions IA
            </button>
          </div>
        </div>
      </div>

      <!-- Panel Drive -->
      <div class="full-width">
        <DriveAdminPanel />
      </div>
    </div>

    <div class="error-panel fade-in-up" v-if="error">
       <strong>Erreur Système :</strong> {{ error }}
    </div>
  </div>
</template>

<style scoped>
.admin-wrapper {
  max-width: 1100px;
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
  margin-bottom: 2.5rem;
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.2);
  position: relative;
  overflow: hidden;
}

.banner-icon {
  background: rgba(227, 25, 55, 0.2);
  padding: 1.25rem;
  border-radius: 16px;
  color: var(--zenika-red);
  flex-shrink: 0;
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

.status-badge {
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  padding: 0.5rem 1rem;
  border-radius: 30px;
  font-size: 0.85rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(52, 211, 153, 0.3);
}

.dashboard-grid {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.full-width {
  width: 100%;
}

.error-panel {
  margin-top: 2rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 1.5rem;
  border-radius: 12px;
  color: #b91c1c;
  display: flex;
  gap: 10px;
}

.fade-in {
  animation: fadeIn 0.4s ease forwards;
}
.fade-in-up {
  animation: fadeInUp 0.5s ease forwards;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.admin-panel {
  background: white;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  overflow: hidden;
  transition: all 0.2s ease;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

.admin-panel:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  border-color: rgba(227, 25, 55, 0.3);
}

.panel-header {
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(0, 0, 0, 0.01);
}

.panel-header h3 {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.1rem;
  color: var(--text-color);
}

.panel-content {
  padding: 1.5rem;
  color: var(--text-light);
  line-height: 1.5;
}

.action-btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  background: rgba(227, 25, 55, 0.1);
  color: var(--zenika-red);
  transition: all 0.2s;
}

.action-btn:hover {
  background: var(--zenika-red);
  color: white;
}
</style>
