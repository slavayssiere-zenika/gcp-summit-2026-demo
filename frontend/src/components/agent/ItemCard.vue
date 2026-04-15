<script setup lang="ts">
import { Package, Tag, Hash } from 'lucide-vue-next'

const props = defineProps<{
  item: {
    id?: number
    user_id?: number
    name: string
    description?: string
    categories?: any
    owner?: any
  }
}>()

const getCategories = (cats: any) => {
  if (!cats) return []
  return Array.isArray(cats) ? cats : [cats]
}
</script>

<template>
  <div class="item-card glass-morphism">
    <div class="status-dot-glow"></div>
    <div class="card-layout">
      <div class="icon-section">
        <div class="icon-wrapper">
          <Package size="24" />
        </div>
      </div>
      <div class="info-section">
        <div class="header-row">
          <h4 class="name">{{ item.name }}</h4>
          <div v-if="item.id || item.user_id" class="id-tag"><Hash size="10" /> {{ item.id || item.user_id }}</div>
        </div>
        <p class="description" v-if="item.description">{{ item.description }}</p>
        
        <div class="meta-row">
          <div class="owner" v-if="item.user_id || item.owner">
            Propriétaire: <span class="owner-id">#{{ item.user_id || item.owner }}</span>
          </div>
        </div>

        <div v-if="item.categories" class="categories-tags">
          <span v-for="(cat, idx) in getCategories(item.categories)" :key="idx" class="tag">
            <Tag size="10" /> {{ (cat && typeof cat === 'object') ? (cat.name || cat.id) : cat }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.item-card {
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 18px;
  padding: 1.25rem;
  position: relative;
  overflow: hidden;
  transition: all 0.2s ease;
}

.item-card:hover {
  background: rgba(255, 255, 255, 0.8);
  border-color: var(--zenika-red);
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.04);
}

.status-dot-glow {
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: var(--zenika-red);
  opacity: 0.6;
}

.card-layout {
  display: flex;
  gap: 1.25rem;
}

.icon-wrapper {
  width: 44px;
  height: 44px;
  background: white;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--zenika-red);
  box-shadow: 0 4px 10px rgba(0,0,0,0.03);
  border: 1px solid rgba(0,0,0,0.03);
}

.info-section {
  flex: 1;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
}

.name {
  font-size: 1rem;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0;
}

.id-tag {
  font-size: 0.65rem;
  color: #94a3b8;
  font-weight: 600;
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 2px;
}

.description {
  font-size: 0.85rem;
  color: #64748b;
  margin: 0.25rem 0 0.75rem;
  line-height: 1.4;
}

.meta-row {
  margin-bottom: 0.75rem;
}

.owner {
  font-size: 0.75rem;
  color: #94a3b8;
}

.owner-id {
  color: #64748b;
  font-weight: 600;
}

.categories-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.tag {
  background: white;
  border: 1px solid #e2e8f0;
  padding: 3px 8px;
  border-radius: 8px;
  font-size: 0.7rem;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}
</style>
