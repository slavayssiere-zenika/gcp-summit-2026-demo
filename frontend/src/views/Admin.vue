<script setup lang="ts">
import { ref } from 'vue'
import {
  Settings, ShieldCheck, BrainCircuit, HardDriveUpload,
  RefreshCw, Users, BarChart3, ArrowRight, Zap
} from 'lucide-vue-next'
import { authService } from '../services/auth'
import DriveAdminPanel from '../components/DriveAdminPanel.vue'
import CVImportMonitor from '../components/CVImportMonitor.vue'

// Tabs: 'drive' | 'prompts' | 'reanalysis'
const activeTab = ref<'drive' | 'prompts' | 'reanalysis'>('drive')

const tabs = [
  {
    key: 'drive' as const,
    label: 'Import Drive',
    icon: HardDriveUpload,
    description: 'Dossiers Google Drive, suivi des CVs importés et gestion des erreurs d\'ingestion.',
  },
  {
    key: 'prompts' as const,
    label: 'Instructions IA',
    icon: BrainCircuit,
    description: 'System prompts des agents et backlog d\'Auto-Correction des erreurs détectées.',
  },
  {
    key: 'reanalysis' as const,
    label: 'Réanalyse & Taxonomie',
    icon: RefreshCw,
    description: 'Relancer l\'analyse Gemini sur les CVs existants et reconstruire l\'arbre de compétences.',
  },
]
</script>

<template>
  <div class="admin-wrapper fade-in">

    <!-- ── Header ────────────────────────────────────────────────── -->
    <div class="header-banner">
      <div class="banner-icon"><Settings size="28" /></div>
      <div class="banner-text">
        <h1>Centre d'Administration</h1>
        <p>Pilotez le pipeline d'import Drive, les instructions de l'IA et les réanalyses de profils.</p>
      </div>
      <div class="role-badge" v-if="authService.state.user?.role === 'admin'">
        <ShieldCheck size="14" />
        <span>Administrateur</span>
      </div>
    </div>

    <!-- ── Pipeline monitor (always visible) ─────────────────────── -->
    <CVImportMonitor class="pipeline-monitor" />

    <!-- ── Tab navigation ────────────────────────────────────────── -->
    <div class="tab-nav" role="tablist" aria-label="Section d'administration">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ 'tab-active': activeTab === tab.key }"
        @click="activeTab = tab.key"
        :aria-selected="activeTab === tab.key"
        role="tab"
        :id="`tab-${tab.key}`"
        :aria-controls="`panel-${tab.key}`"
      >
        <component :is="tab.icon" size="16" />
        {{ tab.label }}
      </button>
    </div>

    <!-- ── Tab: Import Drive ──────────────────────────────────────── -->
    <div
      v-show="activeTab === 'drive'"
      role="tabpanel"
      id="panel-drive"
      aria-labelledby="tab-drive"
      class="tab-panel"
    >
      <DriveAdminPanel />
    </div>

    <!-- ── Tab: Instructions IA ───────────────────────────────────── -->
    <div
      v-show="activeTab === 'prompts'"
      role="tabpanel"
      id="panel-prompts"
      aria-labelledby="tab-prompts"
      class="tab-panel"
    >
      <div class="prompts-landing">
        <div class="landing-icon">
          <BrainCircuit size="40" />
        </div>
        <h2>Instructions IA & Auto-Correction</h2>
        <p>
          Modifiez les System Prompts injectés dans les agents Gemini et consultez le backlog des erreurs
          détectées automatiquement par la plateforme pour améliorer les instructions.
        </p>
        <div class="landing-features">
          <div class="feature-pill">
            <Zap size="14" />
            Prompts dynamiques par agent
          </div>
          <div class="feature-pill">
            <BrainCircuit size="14" />
            Auto-Correction par détection d'erreurs
          </div>
          <div class="feature-pill">
            <BarChart3 size="14" />
            Historique des versions
          </div>
        </div>
        <RouterLink to="/admin/prompts" class="cta-btn" aria-label="Accéder à la gestion des Instructions IA">
          Gérer les Instructions IA
          <ArrowRight size="16" />
        </RouterLink>
      </div>
    </div>

    <!-- ── Tab: Réanalyse & Taxonomie ────────────────────────────── -->
    <div
      v-show="activeTab === 'reanalysis'"
      role="tabpanel"
      id="panel-reanalysis"
      aria-labelledby="tab-reanalysis"
      class="tab-panel"
    >
      <div class="prompts-landing">
        <div class="landing-icon landing-icon-purple">
          <RefreshCw size="40" />
        </div>
        <h2>Réanalyse Globale & Taxonomie</h2>
        <p>
          Relancez l'analyse Gemini sur l'ensemble des CVs pour mettre à jour les compétences extraites,
          ou recalculez l'arbre de taxonomie à partir des données actuelles.
        </p>
        <div class="landing-features">
          <div class="feature-pill feature-pill-red">
            <Users size="14" />
            Filtrage par consultant ou tag
          </div>
          <div class="feature-pill feature-pill-red">
            <RefreshCw size="14" />
            Réanalyse batch (Gemini)
          </div>
          <div class="feature-pill feature-pill-red">
            <Settings size="14" />
            Recalcul taxonomie IA
          </div>
        </div>
        <div class="warning-box">
          ⚠️ Cette opération efface les compétences actuelles et les recalcule.
          À utiliser avec précaution.
        </div>
        <RouterLink to="/admin/reanalysis" class="cta-btn cta-btn-red" aria-label="Accéder à la réanalyse globale">
          Lancer une Réanalyse
          <ArrowRight size="16" />
        </RouterLink>
      </div>
    </div>

  </div>
</template>

<style scoped>
/* ── Global layout ── */
.admin-wrapper {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

.fade-in { animation: fadeIn 0.35s ease forwards; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* ── Header banner ── */
.header-banner {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-radius: 20px;
  padding: 2rem 2.25rem;
  color: white;
  display: flex;
  align-items: center;
  gap: 1.25rem;
  position: relative;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(15,23,42,0.18);
}

.header-banner::before {
  content: '';
  position: absolute;
  top: -40px; right: -40px;
  width: 200px; height: 200px;
  background: radial-gradient(circle, rgba(227,25,55,0.15) 0%, transparent 70%);
  pointer-events: none;
}

.banner-icon {
  background: rgba(227,25,55,0.18);
  padding: 1rem;
  border-radius: 14px;
  color: #E31937;
  flex-shrink: 0;
  display: flex;
}

.banner-text h1 {
  font-size: 1.6rem;
  font-weight: 800;
  margin: 0 0 0.3rem 0;
  letter-spacing: -0.02em;
}

.banner-text p {
  color: #94a3b8;
  margin: 0;
  font-size: 0.95rem;
  line-height: 1.5;
}

.role-badge {
  position: absolute;
  top: 1.25rem; right: 1.5rem;
  background: rgba(52,211,153,0.12);
  color: #34d399;
  padding: 0.4rem 0.9rem;
  border-radius: 30px;
  font-size: 0.78rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 5px;
  border: 1px solid rgba(52,211,153,0.25);
}

/* ── Pipeline monitor ── */
.pipeline-monitor {
  /* CVImportMonitor component — no extra styles needed, handled inside */
}

/* ── Tab navigation ── */
.tab-nav {
  display: flex;
  gap: 4px;
  background: rgba(241,245,249,0.8);
  padding: 5px;
  border-radius: 14px;
  border: 1px solid #e2e8f0;
}

.tab-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0.75rem 1rem;
  border: none;
  background: transparent;
  border-radius: 10px;
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.tab-btn:hover:not(.tab-active) {
  color: #1e293b;
  background: rgba(255,255,255,0.6);
}

.tab-active {
  background: white;
  color: #1e293b;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

/* ── Tab panels ── */
.tab-panel {
  animation: fadeIn 0.25s ease forwards;
}

/* ── Prompts/Reanalysis landing cards ── */
.prompts-landing {
  background: white;
  border-radius: 20px;
  border: 1px solid #e8edf3;
  padding: 3rem 2.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 1.25rem;
  box-shadow: 0 4px 20px rgba(0,0,0,0.04);
}

.landing-icon {
  width: 72px; height: 72px;
  background: rgba(99,102,241,0.1);
  color: #6366f1;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.landing-icon-purple {
  background: rgba(227,25,55,0.08);
  color: #E31937;
}

.prompts-landing h2 {
  font-size: 1.5rem;
  font-weight: 800;
  color: #1e293b;
  margin: 0;
}

.prompts-landing > p {
  color: #64748b;
  max-width: 520px;
  line-height: 1.6;
  margin: 0;
  font-size: 0.95rem;
}

.landing-features {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}

.feature-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: rgba(99,102,241,0.08);
  color: #6366f1;
  border-radius: 30px;
  font-size: 0.78rem;
  font-weight: 600;
}

.feature-pill-red {
  background: rgba(227,25,55,0.08);
  color: #E31937;
}

.warning-box {
  background: rgba(251,146,60,0.08);
  border: 1px solid rgba(251,146,60,0.25);
  color: #c2410c;
  border-radius: 10px;
  padding: 10px 18px;
  font-size: 0.83rem;
  font-weight: 500;
  max-width: 420px;
}

.cta-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0.85rem 1.75rem;
  background: #6366f1;
  color: white;
  border-radius: 12px;
  font-weight: 700;
  font-size: 0.95rem;
  text-decoration: none;
  transition: all 0.2s ease;
  box-shadow: 0 4px 14px rgba(99,102,241,0.3);
}

.cta-btn:hover {
  background: #4f46e5;
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(99,102,241,0.4);
}

.cta-btn-red {
  background: #E31937;
  box-shadow: 0 4px 14px rgba(227,25,55,0.3);
}

.cta-btn-red:hover {
  background: #c3132e;
  box-shadow: 0 8px 20px rgba(227,25,55,0.4);
}

@media (max-width: 768px) {
  .admin-wrapper { padding: 1rem; gap: 1.25rem; }
  .header-banner { flex-wrap: wrap; padding: 1.5rem; }
  .tab-btn { font-size: 0.78rem; padding: 0.6rem 0.5rem; }
  .prompts-landing { padding: 2rem 1.5rem; }
  .tab-nav { overflow-x: auto; }
}
</style>
