<script setup lang="ts">
import { Mail, CheckCircle2, XCircle, ArrowRight, Hash, EyeOff } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

const props = defineProps<{
  consultant: {
    id?: number
    user_id?: number
    full_name?: string
    username?: string
    email?: string
    is_active?: boolean
    is_anonymous?: boolean
  }
}>()

const router = useRouter()

const getInitials = (name?: string) => {
  if (!name) return '?'
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

const goToProfile = () => {
  const id = props.consultant.id || props.consultant.user_id
  if (id) router.push({ name: 'user-detail', params: { id: id.toString() } })
}
</script>

<template>
  <div class="consultant-card" @click="goToProfile" aria-label="Voir le profil du consultant">
    <!-- Avatar -->
    <div class="avatar" :class="{ anonymous: consultant.is_anonymous }">
      {{ getInitials(consultant.full_name || consultant.username) }}
    </div>

    <!-- Info -->
    <div class="info">
      <div class="name-row">
        <span class="name">{{ consultant.full_name || consultant.username }}</span>
        <span class="id-tag"><Hash size="10" />{{ consultant.id || consultant.user_id }}</span>
      </div>
      <div class="email-row" v-if="consultant.email && !consultant.is_anonymous">
        <Mail size="11" />
        <span>{{ consultant.email }}</span>
      </div>
      <div class="email-row anon" v-else-if="consultant.is_anonymous">
        <EyeOff size="11" />
        <span>Profil anonymisé</span>
      </div>
    </div>

    <!-- Status + Arrow -->
    <div class="right-col">
      <span class="status-badge" :class="{ active: consultant.is_active !== false }">
        <CheckCircle2 v-if="consultant.is_active !== false" size="11" />
        <XCircle v-else size="11" />
        {{ consultant.is_active !== false ? 'Dispo' : 'Indispo' }}
      </span>
      <ArrowRight size="14" class="arrow" />
    </div>
  </div>
</template>

<style scoped>
.consultant-card {
  display: flex;
  align-items: center;
  gap: 10px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.consultant-card:hover {
  border-color: var(--zenika-red);
  box-shadow: 0 4px 16px rgba(227, 25, 55, 0.08);
  transform: translateX(3px);
}

/* ── Avatar ── */
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--zenika-red);
  color: white;
  font-size: 0.75rem;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(227, 25, 55, 0.2);
}

.avatar.anonymous {
  background: #94a3b8;
  box-shadow: none;
}

/* ── Info ── */
.info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.name {
  font-size: 0.85rem;
  font-weight: 700;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.id-tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 0.62rem;
  font-weight: 600;
  color: #94a3b8;
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 4px;
  flex-shrink: 0;
}

.email-row {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.72rem;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.email-row.anon {
  color: #94a3b8;
  font-style: italic;
}

/* ── Right col ── */
.right-col {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex-shrink: 0;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px 7px;
  border-radius: 6px;
}

.status-badge.active {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.status-badge:not(.active) {
  background: rgba(100, 116, 139, 0.08);
  color: #64748b;
}

.arrow {
  color: #cbd5e1;
  transition: color 0.15s, transform 0.15s;
}

.consultant-card:hover .arrow {
  color: var(--zenika-red);
  transform: translateX(2px);
}
</style>
