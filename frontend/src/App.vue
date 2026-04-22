<script setup lang="ts">
import { ref } from 'vue'
import {
  LogOut, User as UserIcon, Bot, Network, ServerCog, BookOpen,
  ChevronDown, Settings, BarChart3, Cpu, HardDriveUpload,
  Users, GitMerge, CalendarDays, BrainCircuit, RefreshCw,
  ShieldAlert, Briefcase, ExternalLink
} from 'lucide-vue-next'
import { authService } from './services/auth'
import { useRouter } from 'vue-router'
import ToastNotification from '@/components/ui/ToastNotification.vue'

const router = useRouter()
const searchQuery = ref('')
const handleSearch = () => {
  if (searchQuery.value) {
    router.push({ path: '/', query: { q: searchQuery.value } })
    searchQuery.value = ''
  }
}

const handleLogout = async () => {
  await authService.logout()
}

const isAdmin = () => authService.state.user?.role === 'admin'
const isRh = () => authService.state.user?.role === 'rh' || isAdmin()
</script>

<template>
  <div id="main-app">
    <ToastNotification />
    <div class="header">
      <div class="logo">ZENIKA</div>
      <div class="subtitle">Console Intelligent Agent</div>
      <div class="nav-links">
        <div class="header-search">
          <input 
            type="text" 
            v-model="searchQuery" 
            @keypress.enter="handleSearch"
            placeholder="🔍 Rechercher un profil..."
          >
        </div>
        <div class="nav-pills" v-if="authService.state.isAuthenticated">

          <!-- Agent IA -->
          <RouterLink to="/" class="nav-pill" active-class="active" aria-label="Agent conversationnel">
            <Bot size="16" /> Agent
          </RouterLink>

          <!-- Hub RH (consultants, compétences) -->
          <div class="dropdown" v-if="isRh()">
            <button class="nav-pill dropdown-btn" :class="{ active: ['/user', '/competencies', '/admin/deduplication', '/admin/availability'].some(p => router.currentRoute.value.path.startsWith(p)) }">
              <Users size="16" /> Hub RH <ChevronDown size="14" />
            </button>
            <div class="dropdown-content">
              <div class="dropdown-section-label">Consultants</div>
              <RouterLink to="/" class="nav-pill" aria-label="Rechercher un consultant via l'agent">
                <Bot size="14" /> Recherche par Agent
              </RouterLink>
              <RouterLink to="/competencies" class="nav-pill" active-class="dropdown-active" aria-label="Arbre des compétences">
                <Network size="14" /> Arbre des Compétences
              </RouterLink>
              <div class="dropdown-section-label">Gestion RH</div>
              <RouterLink to="/admin/availability" class="nav-pill" active-class="dropdown-active" aria-label="Planning des disponibilités">
                <CalendarDays size="14" /> Planning Disponibilités
              </RouterLink>
              <RouterLink to="/admin/deduplication" class="nav-pill" active-class="dropdown-active" aria-label="Déduplication des profils en doublon">
                <GitMerge size="14" /> Déduplication Profils
              </RouterLink>
            </div>
          </div>

          <!-- Missions -->
          <RouterLink to="/missions" class="nav-pill" active-class="active" aria-label="Hub des missions clients">
            <Briefcase size="16" /> Missions
          </RouterLink>

          <!-- Administration (admin only) -->
          <div class="dropdown" v-if="isAdmin()">
            <button
              class="nav-pill admin-pill dropdown-btn"
              :class="{ active: router.currentRoute.value.path.startsWith('/admin') }"
              aria-label="Menu Administration"
            >
              <Settings size="16" /> Admin <ChevronDown size="14" />
            </button>
            <div class="dropdown-content dropdown-wide">
              <div class="dropdown-section-label">Pipeline de données</div>
              <RouterLink to="/admin" class="nav-pill" active-class="dropdown-active" aria-label="Gestion du pipeline d'import Drive et supervision CV">
                <HardDriveUpload size="14" /> Import Drive & Supervision CV
              </RouterLink>
              <RouterLink to="/import-cv" class="nav-pill" active-class="dropdown-active" aria-label="Import manuel d'un CV depuis le poste">
                <BookOpen size="14" /> Import CV Manuel
              </RouterLink>
              <RouterLink to="/admin/reanalysis" class="nav-pill" active-class="dropdown-active" aria-label="Réanalyse batch des CVs par Gemini">
                <RefreshCw size="14" /> Réanalyse & Taxonomie IA
              </RouterLink>

              <div class="dropdown-section-label">Configuration Agents</div>
              <RouterLink to="/admin/prompts" class="nav-pill" active-class="dropdown-active" aria-label="Gérer les instructions des agents IA">
                <BrainCircuit size="14" /> Instructions des Agents IA
              </RouterLink>

              <div class="dropdown-section-label">Utilisateurs & Sécurité</div>
              <RouterLink to="/admin/users" class="nav-pill" active-class="dropdown-active" aria-label="Gestion des comptes et rôles">
                <Users size="14" /> Comptes & Rôles
              </RouterLink>
              <RouterLink to="/admin/finops" class="nav-pill" active-class="dropdown-active" aria-label="Sécurité, audit et suivi couts IA (FinOps)">
                <ShieldAlert size="14" /> Sécurité & FinOps IA
              </RouterLink>
            </div>
          </div>

          <!-- Outils Techniques / Documentation -->
          <div class="dropdown">
            <button class="nav-pill dropdown-btn" aria-label="Menu Outils et Documentation">
              <BookOpen size="16" /> Docs <ChevronDown size="14" />
            </button>
            <div class="dropdown-content dropdown-wide">
              <div class="dropdown-section-label">Documentation</div>
              <RouterLink to="/help" class="nav-pill" active-class="dropdown-active">
                <BookOpen size="14" /> Centre d'Aide
              </RouterLink>
              <RouterLink to="/docs/agents" class="nav-pill" active-class="dropdown-active">
                <Cpu size="14" /> Documentation Agents
              </RouterLink>
              <RouterLink to="/specs" class="nav-pill" active-class="dropdown-active">
                <BookOpen size="14" /> Spécifications Techniques
              </RouterLink>

              <div class="dropdown-section-label">Observabilité</div>
              <RouterLink to="/infrastructure" class="nav-pill" active-class="dropdown-active">
                <Network size="14" /> Carte Infrastructure
              </RouterLink>
              <RouterLink to="/aiops" class="nav-pill" active-class="dropdown-active">
                <BarChart3 size="14" /> Indicateurs AIOps
              </RouterLink>
              <RouterLink to="/registry" class="nav-pill" active-class="dropdown-active">
                <ServerCog size="14" /> Serveurs MCP
              </RouterLink>

              <div class="dropdown-section-label" v-if="isAdmin()">API Swagger</div>
              <template v-if="isAdmin()">
                <a href="/users_api/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Users API">
                  <ExternalLink size="13" /> Users API
                </a>
                <a href="/cv_api/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger CV API">
                  <ExternalLink size="13" /> CV API
                </a>
                <a href="/comp_api/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Competencies API">
                  <ExternalLink size="13" /> Competencies API
                </a>
                <a href="/drive_api/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Drive API">
                  <ExternalLink size="13" /> Drive API
                </a>
                <a href="/prompts_api/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Prompts API">
                  <ExternalLink size="13" /> Prompts API
                </a>
                <a href="/api/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Agent Router API">
                  <ExternalLink size="13" /> Agent Router API
                </a>
                <a href="/api/missions/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Missions API">
                  <ExternalLink size="13" /> Missions API
                </a>
                <a href="/items_api/docs" target="_blank" class="nav-pill swagger-link" aria-label="Swagger Items API">
                  <ExternalLink size="13" /> Items API
                </a>
              </template>
            </div>
          </div>

        </div>

        <div v-if="authService.state.isAuthenticated" class="separator"></div>

        <div v-if="authService.state.isAuthenticated" class="user-profile">
          <RouterLink to="/profile" class="user-info-link nav-pill user-pill">
            <UserIcon size="16" />
            <span>{{ authService.state.user?.full_name }}</span>
          </RouterLink>
          <button @click="handleLogout" class="logout-pill" title="Déconnexion">
            <LogOut size="16" />
          </button>
        </div>
      </div>
    </div>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style>
:root {
  --zenika-red: #E31937;
  --bg-gradient: linear-gradient(135deg, #f8f9ff 0%, #f1f4f9 100%);
  --text-primary: #1a1a1a;
  --text-secondary: #5a5a5a;
  --header-bg: rgba(255, 255, 255, 0.9);
  --shadow-sm: 0 4px 12px rgba(0, 0, 0, 0.05);

  /* Shared variables for Admin Panels */
  --surface-light: #ffffff;
  --surface-color: #f8f9fa;
  --border-color: #e2e8f0;
  --text-light: #64748b;
  --text-color: #1e293b;
  --primary-color: var(--zenika-red);
  --primary-light: #f87171;
  --bg-color: var(--bg-gradient);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  background: var(--bg-gradient);
  color: var(--text-primary);
  min-height: 100vh;
}

#main-app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.header {
  background: var(--header-bg);
  backdrop-filter: blur(12px);
  padding: 1.25rem 2.5rem;
  display: flex;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 100;
  border-bottom: 2px solid var(--zenika-red);
  box-shadow: var(--shadow-sm);
}

.logo {
  font-weight: 800;
  font-size: 1.5rem;
  letter-spacing: -0.5px;
  color: var(--zenika-red);
  margin-right: 1.5rem;
}

.subtitle {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary);
  opacity: 0.8;
  padding-left: 1.5rem;
  border-left: 1px solid #e0e0e0;
}

.nav-links {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 16px;
}

.nav-pills {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(0, 0, 0, 0.03);
  padding: 6px;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.nav-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 8px;
  color: var(--text-secondary);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.9rem;
  transition: all 0.25s ease;
}

.nav-pill:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--zenika-red);
  transform: translateY(-2px);
}

.nav-pill.active {
  background: #fff;
  color: var(--zenika-red);
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.1);
  font-weight: 600;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 6px;
}

.user-pill {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
}

.user-pill:hover {
  border-color: rgba(227, 25, 55, 0.3);
}

.logout-pill {
  background: rgba(227, 25, 55, 0.05);
  border: 1px solid rgba(227, 25, 55, 0.1);
  color: var(--zenika-red);
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.logout-pill:hover {
  background: var(--zenika-red);
  color: #fff;
}
.nav-links a {
  text-decoration: none;
  color: var(--text-secondary);
  font-weight: 500;
  font-size: 0.9rem;
  padding: 0.5rem 0.9rem;
  border-radius: 12px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.nav-links a:hover {
  background: rgba(227, 25, 55, 0.05);
  color: var(--zenika-red);
}

.nav-links a.active {
  background: var(--zenika-red);
  color: white;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.2);
}

/* Dropdown Menu CSS */
.dropdown {
  position: relative;
  display: inline-block;
}

.dropdown-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
}

.dropdown-content {
  display: none;
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  background-color: var(--header-bg);
  min-width: 240px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.13);
  border-radius: 14px;
  z-index: 1000;
  border: 1px solid rgba(0, 0, 0, 0.07);
  padding: 8px;
  flex-direction: column;
  gap: 2px;
  backdrop-filter: blur(12px);
}

.dropdown-wide {
  min-width: 280px;
}

/* Align right-side dropdowns to prevent overflow */
.dropdown:last-of-type .dropdown-content,
.dropdown:nth-last-of-type(2) .dropdown-content {
  left: auto;
  right: 0;
}

.dropdown:hover .dropdown-content {
  display: flex;
}

.dropdown-content .nav-pill {
  width: 100%;
  justify-content: flex-start;
  white-space: nowrap;
  font-size: 0.85rem;
  padding: 7px 12px;
  border-radius: 8px;
  gap: 9px;
}

.dropdown-section-label {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #94a3b8;
  padding: 8px 12px 4px;
  margin-top: 2px;
}

.dropdown-section-label:first-child {
  margin-top: 0;
  padding-top: 4px;
}

.dropdown-divider {
  height: 1px;
  background: rgba(0,0,0,0.06);
  margin: 4px 0;
}

.dropdown-active {
  background: rgba(227, 25, 55, 0.07);
  color: var(--zenika-red);
  font-weight: 600;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 1rem;
  background: white;
  padding: 0.4rem 0.5rem 0.4rem 1rem;
  border-radius: 16px;
  border: 1.5px solid #eee;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
}

.logout-btn {
  background: #f5f5f5;
  border: none;
  color: #666;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.logout-btn:hover {
  background: #fff5f5;
  color: var(--zenika-red);
  transform: scale(1.05);
}

.separator {
  width: 1px;
  height: 24px;
  background: #e0e0e0;
  margin: 0 0.75rem;
}

.swagger-links {
  display: flex;
  gap: 0.4rem;
  background: rgba(0, 0, 0, 0.03);
  padding: 0.3rem;
  border-radius: 14px;
}

.swagger-link {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem !important;
  color: #666 !important;
  border: 1px solid transparent;
}

.swagger-link:hover {
  background: white !important;
  border-color: #ddd;
  box-shadow: var(--shadow-sm);
  color: var(--zenika-red) !important;
}

.header-search {
  position: relative;
  margin-right: 1rem;
}

.header-search input {
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.85rem;
  width: 200px;
  transition: all 0.2s;
  color: var(--text-primary);
}

.header-search input:focus {
  background: #fff;
  width: 260px;
  outline: none;
  border-color: var(--zenika-red);
  box-shadow: 0 0 0 4px rgba(227, 25, 55, 0.15), 0 4px 10px rgba(227, 25, 55, 0.1);
  transform: translateY(-1px);
}

.content {
  flex: 1;
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}
.admin-pill {
  border: 1px solid rgba(227, 25, 55, 0.2);
  background: rgba(227, 25, 55, 0.05);
}
.admin-pill:hover {
  background: rgba(227, 25, 55, 0.1);
  border-color: rgba(227, 25, 55, 0.4);
}
.admin-pill.active {
  background: var(--zenika-red);
  color: white;
  border-color: var(--zenika-red);
}
</style>
