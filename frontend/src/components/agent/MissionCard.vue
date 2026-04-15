<script setup lang="ts">
import { Briefcase, Users, Tag, ArrowRight } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

const props = defineProps<{
  mission: {
    id: number
    title: string
    description: string
    extracted_competencies?: string[]
    proposed_team?: any[]
  }
}>()

const router = useRouter()

const goToDetail = () => {
  router.push({ name: 'mission-detail', params: { id: props.mission.id.toString() } })
}
</script>

<template>
  <div class="mission-card glass-morphism clickable" @click="goToDetail">
    <div class="card-header">
      <div class="icon-box">
        <Briefcase size="24" />
      </div>
      <div class="title-area">
        <h3 class="title">{{ mission.title }}</h3>
        <span class="id-badge">#{{ mission.id }}</span>
      </div>
    </div>

    <div class="card-body">
      <p class="description">{{ mission.description }}</p>
      
      <div v-if="mission.extracted_competencies && mission.extracted_competencies.length > 0" class="competencies">
        <span v-for="comp in mission.extracted_competencies" :key="comp" class="comp-tag">
          <Tag size="12" /> {{ comp }}
        </span>
      </div>

      <div v-if="mission.proposed_team && mission.proposed_team.length > 0" class="team-summary">
        <div class="team-label">
          <Users size="14" /> {{ mission.proposed_team.length }} expert{{ mission.proposed_team.length > 1 ? 's' : '' }} suggéré{{ mission.proposed_team.length > 1 ? 's' : '' }}
        </div>
        <div class="team-avatars">
          <div v-for="(member, idx) in mission.proposed_team.slice(0, 3)" :key="idx" class="mini-avatar" :title="member.full_name">
            {{ member.full_name?.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2) || '?' }}
          </div>
          <div v-if="mission.proposed_team.length > 3" class="more-members">
            +{{ mission.proposed_team.length - 3 }}
          </div>
        </div>
      </div>
    </div>

    <div class="card-footer">
      <span class="action-text">Voir les détails de la mission</span>
      <ArrowRight size="16" />
    </div>
  </div>
</template>

<style scoped>
.mission-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(227, 25, 55, 0.1);
  border-radius: 20px;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  height: 100%;
}

.mission-card.clickable {
  cursor: pointer;
}

.mission-card.clickable:hover {
  transform: translateY(-5px);
  box-shadow: 0 12px 30px rgba(227, 25, 55, 0.08);
  border-color: var(--zenika-red);
}

.card-header {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.icon-box {
  width: 48px;
  height: 48px;
  background: var(--zenika-red);
  color: white;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 10px rgba(227, 25, 55, 0.2);
}

.title-area {
  flex: 1;
}

.title {
  font-size: 1.15rem;
  font-weight: 800;
  margin: 0;
  color: #1a1a1a;
  letter-spacing: -0.02em;
}

.id-badge {
  font-size: 0.75rem;
  font-weight: 600;
  color: #888;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 6px;
}

.description {
  font-size: 0.95rem;
  color: #4a5568;
  line-height: 1.6;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.competencies {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 1rem;
}

.comp-tag {
  font-size: 0.75rem;
  font-weight: 600;
  color: #4b5563;
  background: #fff;
  border: 1px solid #e5e7eb;
  padding: 4px 10px;
  border-radius: 99px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.team-summary {
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.team-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: #64748b;
  display: flex;
  align-items: center;
  gap: 6px;
}

.team-avatars {
  display: flex;
  align-items: center;
}

.mini-avatar {
  width: 28px;
  height: 28px;
  background: #f1f5f9;
  border: 2px solid white;
  border-radius: 50%;
  margin-left: -8px;
  font-size: 0.65rem;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #475569;
}

.mini-avatar:first-child {
  margin-left: 0;
}

.more-members {
  font-size: 0.75rem;
  font-weight: 700;
  color: #64748b;
  margin-left: 6px;
}

.card-footer {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--zenika-red);
  font-weight: 700;
  font-size: 0.85rem;
  opacity: 0;
  transform: translateX(-10px);
  transition: all 0.3s ease;
}

.mission-card:hover .card-footer {
  opacity: 1;
  transform: translateX(0);
}

.action-text {
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
</style>
