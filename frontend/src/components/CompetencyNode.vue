<script setup lang="ts">
import { ref } from 'vue'
import { ChevronRight, ChevronDown, Folder, FileCode2 } from 'lucide-vue-next'

const props = defineProps({
  node: {
    type: Object,
    required: true
  },
  depth: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['select-leaf'])

// Initialize state (folded by default if it has children)
const isExpanded = ref(false)

const toggle = () => {
  if (props.node.sub_competencies && props.node.sub_competencies.length) {
    isExpanded.value = !isExpanded.value
  } else {
    emit('select-leaf', props.node)
  }
}

const hasChildren = props.node.sub_competencies && props.node.sub_competencies.length > 0
</script>

<template>
  <div class="competency-node">
    <div 
      class="node-header" 
      @click="toggle"
      :class="{ 
        'is-clickable': hasChildren || !hasChildren, 
        'is-root': depth === 0,
        'is-leaf': !hasChildren
      }"
    >
      <span class="icon-toggle" v-if="hasChildren">
        <ChevronDown v-if="isExpanded" size="16" />
        <ChevronRight v-else size="16" />
      </span>
      <span class="icon-spacer" v-else></span>
      
      <span class="icon-folder">
        <Folder v-if="hasChildren" size="16" :class="{ 'open': isExpanded }" />
        <FileCode2 v-else size="16" class="leaf" />
      </span>

      <div class="node-info">
        <span class="name">{{ node.name }}</span>
        <div class="aliases" v-if="node.aliases">
          <span v-for="alias in node.aliases.split(',')" :key="alias" class="alias-badge">
            {{ alias.trim() }}
          </span>
        </div>
        <span class="description" v-if="node.description">{{ node.description }}</span>
      </div>
      
      <div class="node-id">#{{ node.id }}</div>
    </div>

    <!-- Recursive Call for Children -->
    <div class="children" v-if="isExpanded && hasChildren">
      <CompetencyNode 
        v-for="child in node.sub_competencies" 
        :key="child.id" 
        :node="child"
        :depth="depth + 1"
        @select-leaf="$emit('select-leaf', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.competency-node {
  margin-top: 4px;
}

.node-header {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  transition: all 0.2s ease;
  backdrop-filter: blur(8px);
}

.node-header.is-clickable {
  cursor: pointer;
}

.node-header.is-clickable:hover {
  background: rgba(255, 255, 255, 0.9);
  border-color: rgba(227, 25, 55, 0.4);
  transform: translateX(4px);
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.08);
}

.node-header.is-leaf:hover {
  border-color: #4CAF50;
  background: rgba(76, 175, 80, 0.05);
}

.node-header.is-root {
  background: rgba(227, 25, 55, 0.05);
  border: 1px solid rgba(227, 25, 55, 0.15);
  margin-top: 12px;
}

.icon-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: #888;
  margin-right: 4px;
  transition: color 0.2s;
}

.is-clickable:hover .icon-toggle {
  color: #E31937;
}

.icon-spacer {
  width: 28px;
}

.icon-folder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #888;
  margin-right: 12px;
}

.icon-folder .open {
  color: #E31937;
}

.icon-folder .leaf {
  color: #4CAF50;
}

.node-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.name {
  font-weight: 600;
  font-size: 15px;
  color: #1A1A1A;
}

.description {
  font-size: 13px;
  color: #666;
  margin-top: 2px;
}

.aliases {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 4px 0;
}

.alias-badge {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  background: rgba(0, 0, 0, 0.05);
  color: #555;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.1);
}

.node-id {
  font-family: monospace;
  font-size: 13px;
  font-weight: 600;
  color: #E31937;
  background: rgba(227, 25, 55, 0.08);
  padding: 3px 8px;
  border-radius: 6px;
  margin-left: 12px;
}

.children {
  position: relative;
  /* Visual hierarchy line strong red */
  border-left: 2px solid rgba(227, 25, 55, 0.15);
  margin-left: 24px;
  padding-left: 16px;
  padding-top: 4px;
  margin-top: 4px;
}
</style>
