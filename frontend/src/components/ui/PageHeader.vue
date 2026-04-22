<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight, ShieldCheck } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { authService } from '../../services/auth'

interface BreadcrumbItem {
  label: string
  to?: string
}

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  icon?: any
  breadcrumb?: BreadcrumbItem[]
  showRole?: boolean
}>(), {
  showRole: true,
  breadcrumb: () => [],
})

const router = useRouter()

const userRole = computed(() => authService.state.user?.role)
const roleLabel = computed(() => {
  if (userRole.value === 'admin') return 'Admin'
  if (userRole.value === 'rh') return 'RH'
  return null
})
</script>

<template>
  <div class="page-header">
    <!-- Breadcrumb -->
    <nav v-if="breadcrumb.length" class="breadcrumb" aria-label="Fil d'Ariane">
      <span
        v-for="(item, i) in breadcrumb"
        :key="i"
        class="crumb-group"
      >
        <button
          v-if="item.to"
          class="crumb crumb-link"
          @click="router.push(item.to)"
        >{{ item.label }}</button>
        <span v-else class="crumb crumb-current">{{ item.label }}</span>
        <ChevronRight v-if="i < breadcrumb.length - 1" size="12" class="crumb-sep" />
      </span>
    </nav>

    <!-- Banner -->
    <div class="header-banner">
      <div v-if="icon" class="banner-icon">
        <component :is="icon" size="26" />
      </div>
      <div class="banner-text">
        <h1>{{ title }}</h1>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="showRole && roleLabel" class="role-badge">
        <ShieldCheck size="13" />
        <span>{{ roleLabel }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 2rem;
}

/* ── Breadcrumb ── */
.breadcrumb {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
}

.crumb-group {
  display: flex;
  align-items: center;
  gap: 2px;
}

.crumb {
  font-size: 0.78rem;
  font-weight: 500;
  padding: 3px 0;
  background: none;
  border: none;
  cursor: default;
}

.crumb-link {
  color: #94a3b8;
  cursor: pointer;
  text-decoration: none;
  transition: color 0.15s;
  padding: 3px 6px;
  border-radius: 5px;
}

.crumb-link:hover {
  color: #E31937;
  background: rgba(227,25,55,0.06);
}

.crumb-current {
  color: #475569;
  font-weight: 600;
}

.crumb-sep {
  color: #cbd5e1;
  flex-shrink: 0;
}

/* ── Banner ── */
.header-banner {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-radius: 20px;
  padding: 1.75rem 2rem;
  color: white;
  display: flex;
  align-items: center;
  gap: 1.25rem;
  position: relative;
  overflow: hidden;
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.18);
}

.header-banner::before {
  content: '';
  position: absolute;
  top: -40px; right: -40px;
  width: 180px; height: 180px;
  background: radial-gradient(circle, rgba(227,25,55,0.12) 0%, transparent 70%);
  pointer-events: none;
}

.banner-icon {
  background: rgba(227, 25, 55, 0.18);
  padding: 0.9rem;
  border-radius: 14px;
  color: #E31937;
  flex-shrink: 0;
  display: flex;
}

.banner-text h1 {
  font-size: 1.5rem;
  font-weight: 800;
  margin: 0 0 0.25rem 0;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.banner-text p {
  color: #94a3b8;
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.5;
}

.role-badge {
  position: absolute;
  top: 1.1rem;
  right: 1.5rem;
  background: rgba(52, 211, 153, 0.12);
  color: #34d399;
  padding: 0.35rem 0.8rem;
  border-radius: 30px;
  font-size: 0.75rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 5px;
  border: 1px solid rgba(52, 211, 153, 0.22);
}
</style>
