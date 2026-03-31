<script setup lang="ts">
import { computed } from 'vue'
import { docs } from '../data/docs'

const props = defineProps<{
  service: string
}>()

const currentDoc = computed(() => docs[props.service] || null)

const getBadgeClass = (method: string) => {
  const classes: Record<string, string> = {
    'GET': 'badge-get',
    'POST': 'badge-post',
    'PUT': 'badge-put',
    'DELETE': 'badge-delete'
  }
  return classes[method] || ''
}
</script>

<template>
  <div v-if="currentDoc" class="docs-container">
    <div class="intro">
      <h2>{{ currentDoc.title }}</h2>
      <p>{{ currentDoc.description }}</p>
    </div>
    
    <div v-for="tool in currentDoc.tools" :key="tool.name" class="section">
      <h3>
        <span :class="['badge', getBadgeClass(tool.method)]">{{ tool.method }}</span>
        {{ tool.name }}
      </h3>
      <div class="tool">
        <p>{{ tool.description }}</p>
        <div v-if="tool.arguments.length" class="param-title">Arguments:</div>
        <ul v-if="tool.arguments.length" class="param-list">
          <li v-for="arg in tool.arguments" :key="arg.name">
            <code>{{ arg.name }}</code> ({{ arg.type }}){{ arg.required ? ', requis' : '' }}: {{ arg.description }}
          </li>
        </ul>
        <div class="example-title">Example:</div>
        <pre><code>{{ tool.example }}</code></pre>
      </div>
    </div>
  </div>
  <div v-else class="not-found">
    <h2>Documentation non trouvée</h2>
    <p>Le service recherché n'a pas été trouvé.</p>
  </div>
</template>

<style scoped>
.docs-container {
  max-width: 900px;
  margin: 0 auto;
}

.intro {
  margin-bottom: 3rem;
  background: white;
  padding: 2.5rem;
  border-radius: 24px;
  box-shadow: var(--shadow-sm);
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.intro h2 {
  font-size: 2.2rem;
  font-weight: 800;
  margin-bottom: 1rem;
  color: var(--zenika-red);
  letter-spacing: -1px;
}

.intro p {
  line-height: 1.8;
  font-size: 1.1rem;
  color: var(--text-secondary);
}

.section {
  margin-bottom: 2rem;
  background: white;
  padding: 2.5rem;
  border-radius: 24px;
  box-shadow: var(--shadow-sm);
  border: 1px solid rgba(0, 0, 0, 0.03);
  transition: transform 0.2s;
}

.section:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
}

h3 {
  font-size: 1.4rem;
  font-weight: 700;
  margin-bottom: 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.badge {
  font-size: 0.7rem;
  padding: 4px 10px;
  border-radius: 8px;
  font-weight: 800;
  text-transform: uppercase;
}

.badge-get { background: #E3F2FD; color: #1976D2; }
.badge-post { background: #E8F5E9; color: #2E7D32; }
.badge-put { background: #FFF3E0; color: #F57C00; }
.badge-delete { background: #FFEBEE; color: #D32F2F; }

.tool p {
  margin-bottom: 1.5rem;
  font-size: 1rem;
  color: var(--text-secondary);
}

.param-title, .example-title {
  font-weight: 600;
  font-size: 0.875rem;
  margin-bottom: 0.5rem;
  color: var(--text-primary);
}

.param-list {
  margin-left: 1rem;
  margin-bottom: 1.5rem;
  list-style: none;
}

.param-list li {
  margin-bottom: 0.4rem;
  font-size: 0.9rem;
  position: relative;
  padding-left: 1.2rem;
}

.param-list li::before {
  content: '→';
  position: absolute;
  left: 0;
  color: var(--zenika-red);
}

code {
  font-family: 'JetBrains Mono', monospace;
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
}

pre {
  background: #1a1a1a;
  color: #f8f8f2;
  padding: 1.25rem;
  border-radius: 12px;
  overflow-x: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.9rem;
}
</style>
