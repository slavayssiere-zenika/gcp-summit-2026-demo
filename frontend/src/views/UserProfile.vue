<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { User, Activity, Mail, Award, CheckCircle2, FileText } from 'lucide-vue-next'
import { authService } from '../services/auth'

const route = useRoute()
const userId = route.params.id

const userProfile = ref<any>(null)
const competencies = ref<any[]>([])
const cvData = ref<any>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const headers = {
      'Authorization': `Bearer ${authService.state.token}`
    }
    
    // Fetch User Identity Information
    const userRes = await fetch(`/users-api/users/${userId}`, { headers })
    if (!userRes.ok) throw new Error('Utilisateur introuvable dans le Hub.')
    userProfile.value = await userRes.json()

    // Fetch Assigned Technical/Functional Skills
    const compRes = await fetch(`/comp-api/competencies/user/${userId}`, { headers })
    if (compRes.ok) {
      competencies.value = await compRes.json()
    }

    // Fetch the candidate's Google Docs CV Link (silently fail if 404 because not all users are candidates)
    try {
      const cvRes = await fetch(`/cv-api/cvs/user/${userId}`, { headers })
      if (cvRes.ok) {
        cvData.value = await cvRes.json()
      }
    } catch(e) {}
  } catch (err: any) {
    error.value = err.message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="user-profile-page">
    <div class="header-section">
      <div class="header-content">
        <h1>Profil Collaborateur</h1>
        <p>Aperçu des attributions et de la nomenclature technique pour {{ userProfile?.full_name || 'ce candidat' }}</p>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>Synchronisation des archives en cours...</p>
    </div>
    
    <div v-else-if="error" class="error-msg">
      <p>{{ error }}</p>
    </div>

    <div v-else class="profile-grid">
      <!-- Identity Glassmorphism Card -->
      <div class="glass-card identity-card">
        <div class="avatar-wrap">
          <User size="48" class="avatar-icon"/>
        </div>
        <h2>{{ userProfile.full_name || userProfile.username }}</h2>
        <span class="status-badge" :class="{ active: userProfile.is_active }">
           {{ userProfile.is_active ? 'Actif' : 'Inactif' }}
        </span>

        <div class="contact-info">
           <div class="info-row"><Mail size="16"/> <span>{{ userProfile.email }}</span></div>
           <div class="info-row"><Activity size="16"/> <span>ID Système : #{{ userProfile.id }}</span></div>
           
           <a v-if="cvData?.source_url" :href="cvData.source_url" target="_blank" class="cv-link-btn">
             <FileText size="16"/> <span>Voir le CV original</span>
           </a>
        </div>
      </div>

      <!-- Skills Matrix Card -->
      <div class="glass-card skills-card">
        <div class="skills-header">
           <Award size="28" color="var(--zenika-red)" />
           <h2>Cartographie des Compétences RAG</h2>
        </div>
        
        <div v-if="competencies.length === 0" class="empty-skills">
           <p>Aucune compétence n'est encore cartographiée pour ce profil sur la base de son CV.</p>
        </div>
        <div v-else class="skills-list">
           <div v-for="skill in competencies" :key="skill.id" class="skill-tag">
             <CheckCircle2 size="16" class="skill-check" />
             <span>{{ skill.name }}</span>
           </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.user-profile-page {
  padding: 2rem 4rem;
  max-width: 1200px;
  margin: 0 auto;
  animation: fadeIn 0.4s ease-out;
}

.header-section {
  margin-bottom: 2.5rem;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  padding-bottom: 1.5rem;
}

.header-content h1 {
  font-size: 2.2rem;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
  letter-spacing: -0.5px;
}

.header-content p {
  color: var(--text-secondary);
  font-size: 1.05rem;
}

.profile-grid {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 2rem;
  align-items: start;
}

.glass-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 20px;
  padding: 2.5rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.glass-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.08);
}

.identity-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.avatar-wrap {
  width: 90px;
  height: 90px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(227, 25, 55, 0.1), rgba(227, 25, 55, 0.05));
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1.25rem;
  border: 4px solid white;
  box-shadow: 0 4px 14px rgba(227, 25, 55, 0.15);
}

.avatar-icon {
  color: var(--zenika-red);
}

.identity-card h2 {
  font-size: 1.4rem;
  margin-bottom: 0.5rem;
  font-weight: 700;
}

.status-badge {
  padding: 4px 14px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  background: rgba(0,0,0,0.05);
  color: #666;
  margin-bottom: 2rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.status-badge.active {
  background: rgba(46, 204, 113, 0.15);
  color: #27ae60;
}

.contact-info {
  width: 100%;
  border-top: 1px solid rgba(0,0,0,0.06);
  padding-top: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 0.9rem;
  background: rgba(255,255,255,0.6);
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.03);
}

.skills-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 2rem;
}

.skills-header h2 {
  font-size: 1.4rem;
  font-weight: 700;
  letter-spacing: -0.3px;
}

.empty-skills {
  color: var(--text-secondary);
  font-style: italic;
  padding: 3rem;
  background: rgba(0,0,0,0.02);
  border-radius: 16px;
  text-align: center;
  border: 1px dashed rgba(0,0,0,0.1);
}

.skills-list {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.skill-tag {
  display: flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #ffffff, #fdfdfd);
  border: 1px solid rgba(0,0,0,0.06);
  padding: 10px 18px;
  border-radius: 24px;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
  box-shadow: 0 4px 12px rgba(0,0,0,0.02);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.skill-tag:hover {
  transform: translateY(-2px) scale(1.02);
  border-color: rgba(227, 25, 55, 0.3);
  box-shadow: 0 8px 16px rgba(227, 25, 55, 0.08);
  color: var(--zenika-red);
}

.skill-check {
  color: var(--zenika-red);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 5rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.spinner {
  width: 44px;
  height: 44px;
  border: 3px solid rgba(227, 25, 55, 0.1);
  border-top-color: var(--zenika-red);
  border-radius: 50%;
  animation: spin 0.8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
  margin-bottom: 1.2rem;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.error-msg {
  background: rgba(227, 25, 55, 0.05);
  color: var(--zenika-red);
  padding: 2rem;
  border-radius: 16px;
  border: 1px solid rgba(227, 25, 55, 0.15);
  text-align: center;
  font-weight: 600;
  font-size: 1.1rem;
}

.cv-link-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: var(--zenika-red);
  color: white;
  text-decoration: none;
  padding: 12px 20px;
  border-radius: 12px;
  font-weight: 600;
  margin-top: 0.5rem;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.2);
}

.cv-link-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(227, 25, 55, 0.3);
  background: #c91630;
}
</style>
