<script setup lang="ts">
import { computed } from 'vue'
import { CalendarX, CheckCircle, AlertTriangle, Briefcase, Clock, User } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

const props = defineProps({
  availability: {
    type: Object,
    required: true
  }
})

const router = useRouter()

const goToUser = (id: number) => {
  if (id) {
    router.push({ name: 'user-detail', params: { id: id.toString() } })
  }
}

const statusClass = computed(() => {
  if (props.availability.conflict_detected) return 'status-danger'
  if (!props.availability.is_available) return 'status-warning'
  return 'status-success'
})

const statusIcon = computed(() => {
  if (props.availability.conflict_detected) return AlertTriangle
  if (!props.availability.is_available) return Clock
  return CheckCircle
})

const formatPeriod = (period: any) => {
  if (period.start_date && period.end_date) {
    return `${period.start_date} au ${period.end_date}`
  }
  return 'Période non spécifiée'
}
</script>

<template>
  <div class="availability-card" @click="goToUser(availability.user_id)">
    <div class="card-header" :class="statusClass">
      <div class="status-indicator">
        <component :is="statusIcon" size="18" />
        <span class="status-text">
          {{ availability.conflict_detected ? 'Conflit Détecté' : (availability.is_available ? 'Disponible' : 'Indisponible') }}
        </span>
      </div>
      <div class="user-id">
        <User size="12" />
        <span>ID {{ availability.user_id }}</span>
      </div>
    </div>
    
    <div class="card-body">
      <p class="summary-text">{{ availability.summary }}</p>
      
      <div class="details-grid">
        <div class="detail-section" v-if="availability.active_missions && availability.active_missions.length > 0">
          <h4><Briefcase size="14" /> Missions Actives</h4>
          <ul class="tag-list">
            <li v-for="(mission, idx) in availability.active_missions" :key="idx" class="tag mission-tag">
              Mission #{{ mission.mission_id }} ({{ mission.workload_percentage }}% - {{ mission.status }})
            </li>
          </ul>
        </div>
        
        <div class="detail-section" v-if="availability.unavailability_periods && availability.unavailability_periods.length > 0">
          <h4><CalendarX size="14" /> Indisponibilités</h4>
          <ul class="tag-list">
            <li v-for="(period, idx) in availability.unavailability_periods" :key="idx" class="tag period-tag">
              {{ period.type || 'Absence' }}: {{ formatPeriod(period) }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.availability-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.03);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.availability-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(227, 25, 55, 0.08);
  border-color: rgba(227, 25, 55, 0.2);
  background: rgba(255, 255, 255, 0.95);
}

.card-header {
  padding: 0.75rem 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: white;
}

.card-header.status-success {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.card-header.status-warning {
  background: linear-gradient(135deg, #f59e0b 0%, #ea580c 100%);
}

.card-header.status-danger {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 0.9rem;
  letter-spacing: 0.01em;
}

.user-id {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.75rem;
  background: rgba(255, 255, 255, 0.2);
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  font-weight: 600;
}

.card-body {
  padding: 1.25rem;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.summary-text {
  font-size: 0.9rem;
  color: #334155;
  line-height: 1.5;
  margin: 0;
  font-style: italic;
  border-left: 3px solid #e2e8f0;
  padding-left: 10px;
}

.details-grid {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: auto;
}

.detail-section h4 {
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.5rem 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.tag-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  font-size: 0.75rem;
  padding: 0.3rem 0.6rem;
  border-radius: 6px;
  font-weight: 500;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.mission-tag {
  background: #f0f9ff;
  color: #0284c7;
  border: 1px solid #bae6fd;
}

.period-tag {
  background: #fff7ed;
  color: #ea580c;
  border: 1px solid #fed7aa;
}
</style>
