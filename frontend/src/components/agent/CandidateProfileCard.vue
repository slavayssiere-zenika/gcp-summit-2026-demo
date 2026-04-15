<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Briefcase, ChevronDown, Star, Hash, Clock, EyeOff } from 'lucide-vue-next'

const props = defineProps<{
  profile: {
    user_id?: number
    summary?: string
    current_role?: string
    years_of_experience?: number
    competencies_keywords?: string[]
    missions?: { title: string; company: string; description?: string; competencies?: string[] }[]
    is_anonymous?: boolean
  }
}>()

const router = useRouter()
const expanded = ref(false)

const getInitials = (role?: string) => {
  if (!role) return '?'
  return role.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

const goToProfile = () => {
  if (props.profile.user_id && !props.profile.is_anonymous) {
    router.push({ name: 'user-detail', params: { id: props.profile.user_id.toString() } })
  }
}
</script>

<template>
  <div class="profile-card" :class="{ clickable: !profile.is_anonymous, anonymous: profile.is_anonymous }" @click="!profile.is_anonymous && goToProfile()">
    <!-- Header -->
    <div class="card-header">
      <div class="avatar-wrapper">
        <div class="avatar-glow"></div>
        <div class="avatar">{{ getInitials(profile.current_role) }}</div>
      </div>
      <div class="meta">
        <div class="role-row">
          <span class="current-role">{{ profile.current_role || 'Consultant' }}</span>
          <span v-if="profile.is_anonymous" class="anon-badge"><EyeOff size="11" /> Anonyme</span>
        </div>
        <div class="sub-meta">
          <span v-if="profile.years_of_experience" class="exp-badge"><Clock size="11" /> {{ profile.years_of_experience }} ans</span>
          <span v-if="profile.user_id" class="id-tag"><Hash size="11" /> {{ profile.user_id }}</span>
        </div>
      </div>
    </div>

    <!-- Summary -->
    <p v-if="profile.summary" class="summary">{{ profile.summary }}</p>

    <!-- Skills -->
    <div v-if="profile.competencies_keywords && profile.competencies_keywords.length" class="skills-section">
      <div class="section-label"><Star size="12" /> Compétences clés</div>
      <div class="skills-chips">
        <span v-for="skill in profile.competencies_keywords" :key="skill" class="skill-chip">{{ skill }}</span>
      </div>
    </div>

    <!-- Missions toggle -->
    <div v-if="profile.missions && profile.missions.length" class="missions-section">
      <button class="missions-toggle" @click.stop="expanded = !expanded" aria-label="Voir les missions">
        <Briefcase size="12" />
        <span>{{ profile.missions.length }} mission{{ profile.missions.length > 1 ? 's' : '' }}</span>
        <ChevronDown size="13" :class="['chevron', { open: expanded }]" />
      </button>

      <transition name="slide">
        <div v-if="expanded" class="missions-list">
          <div v-for="(m, i) in profile.missions" :key="i" class="mission-item">
            <div class="mission-header">
              <span class="mission-title">{{ m.title }}</span>
              <span class="mission-company">{{ m.company }}</span>
            </div>
            <div v-if="m.competencies && m.competencies.length" class="mission-skills">
              <span v-for="c in m.competencies" :key="c" class="mission-skill">{{ c }}</span>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<style scoped>
.profile-card {
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(227, 25, 55, 0.1);
  border-radius: 20px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

.profile-card.clickable { cursor: pointer; }
.profile-card.clickable:hover {
  transform: translateY(-5px);
  box-shadow: 0 12px 30px rgba(227, 25, 55, 0.1);
  border-color: var(--zenika-red);
}
.profile-card.anonymous { border-color: #e2e8f0; }

/* ── Header ── */
.card-header {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
}

.avatar-wrapper { position: relative; width: 48px; height: 48px; flex-shrink: 0; }
.avatar-glow {
  position: absolute; inset: -3px;
  background: linear-gradient(135deg, var(--zenika-red), #ff6b6b);
  border-radius: 14px; opacity: 0.12; filter: blur(6px);
}
.avatar {
  position: relative; width: 100%; height: 100%;
  background: var(--zenika-red); color: white;
  border-radius: 14px; display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 1rem; z-index: 2;
  box-shadow: 0 3px 10px rgba(227, 25, 55, 0.2);
}
.anonymous .avatar { background: #94a3b8; box-shadow: none; }

.meta { flex: 1; min-width: 0; }
.role-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap; }
.current-role { font-size: 0.9rem; font-weight: 700; color: #1e293b; }
.anon-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 0.62rem; font-weight: 700; color: #94a3b8;
  background: #f1f5f9; padding: 2px 6px; border-radius: 6px;
}
.sub-meta { display: flex; align-items: center; gap: 6px; }
.exp-badge, .id-tag {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 0.68rem; font-weight: 600; color: #64748b;
  background: #f8fafc; border: 1px solid #e2e8f0;
  padding: 2px 6px; border-radius: 6px;
}

/* ── Summary ── */
.summary {
  font-size: 0.8rem; color: #475569; line-height: 1.5;
  margin: 0; display: -webkit-box;
  -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}

/* ── Skills ── */
.section-label {
  display: flex; align-items: center; gap: 4px;
  font-size: 0.66rem; font-weight: 700; color: #94a3b8;
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px;
}
.skills-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.skill-chip {
  background: rgba(227, 25, 55, 0.06); border: 1px solid rgba(227, 25, 55, 0.15);
  color: #be123c; font-size: 0.7rem; font-weight: 600;
  padding: 3px 8px; border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
}

/* ── Missions ── */
.missions-toggle {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.75rem; font-weight: 600; color: #64748b;
  background: #f8fafc; border: 1px solid #e2e8f0;
  padding: 5px 10px; border-radius: 8px; cursor: pointer;
  transition: all 0.15s; width: fit-content;
}
.missions-toggle:hover { border-color: var(--zenika-red); color: var(--zenika-red); }
.chevron { color: #94a3b8; transition: transform 0.2s; }
.chevron.open { transform: rotate(180deg); }

.slide-enter-active, .slide-leave-active { transition: all 0.2s ease; overflow: hidden; }
.slide-enter-from, .slide-leave-to { max-height: 0; opacity: 0; }
.slide-enter-to, .slide-leave-from { max-height: 600px; opacity: 1; }

.missions-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.mission-item {
  background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 10px; padding: 8px 10px;
}
.mission-header { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; flex-wrap: wrap; }
.mission-title { font-size: 0.75rem; font-weight: 700; color: #1e293b; }
.mission-company {
  font-size: 0.68rem; font-weight: 600; color: var(--zenika-red);
  background: rgba(227, 25, 55, 0.08); padding: 1px 6px; border-radius: 4px;
}
.mission-skills { display: flex; flex-wrap: wrap; gap: 4px; }
.mission-skill {
  font-size: 0.65rem; font-weight: 500; color: #475569;
  background: white; border: 1px solid #e2e8f0;
  padding: 1px 6px; border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
}
</style>
