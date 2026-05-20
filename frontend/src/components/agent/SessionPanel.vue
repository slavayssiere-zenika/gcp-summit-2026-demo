<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus, Pencil, Trash2, Check, X, MessageSquare } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chatStore'
import { useUxStore } from '@/stores/uxStore'
import type { ChatSession } from '@/types'

const chatStore = useChatStore()
const uxStore = useUxStore()

// Session en cours de renommage
const editingId = ref<string | null>(null)
const editingName = ref('')

// Session en cours de confirmation de suppression
const confirmDeleteId = ref<string | null>(null)

const sortedSessions = computed(() =>
  [...chatStore.sessions].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )
)

const canCreateMore = computed(() => chatStore.sessions.length < 10)

function startEdit(session: ChatSession) {
  editingId.value = session.id
  editingName.value = session.name
}

function cancelEdit() {
  editingId.value = null
  editingName.value = ''
}

async function confirmEdit(id: string) {
  const name = editingName.value.trim()
  if (!name) return
  await chatStore.renameSession(id, name)
  editingId.value = null
}

function handleEditKeydown(e: KeyboardEvent, id: string) {
  if (e.key === 'Enter') confirmEdit(id)
  if (e.key === 'Escape') cancelEdit()
}

function askDeleteConfirm(id: string) {
  confirmDeleteId.value = id
}

function cancelDelete() {
  confirmDeleteId.value = null
}

async function confirmDelete(id: string) {
  confirmDeleteId.value = null
  await chatStore.deleteSession(id)
}

async function handleSwitch(id: string) {
  if (chatStore.activeSessionId === id) return
  await chatStore.switchSession(id)
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('fr-FR', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return ''
  }
}
</script>

<template>
  <aside class="session-panel" aria-label="Sessions de travail">
    <div class="panel-header">
      <div class="panel-title">
        <MessageSquare size="15" />
        <span>Sessions</span>
        <span class="session-count" :class="{ 'at-limit': !canCreateMore }">
          {{ chatStore.sessions.length }}/10
        </span>
      </div>
      <button
        class="new-session-btn"
        :disabled="!canCreateMore"
        :title="canCreateMore ? 'Nouvelle session' : 'Limite atteinte'"
        @click="chatStore.createSession()"
      >
        <Plus size="15" />
      </button>
    </div>

    <div class="session-list">
      <div
        v-for="session in sortedSessions"
        :key="session.id"
        :class="['session-item', { active: session.id === chatStore.activeSessionId }]"
        @click="handleSwitch(session.id)"
        :title="`Créé le ${formatDate(session.created_at)}`"
      >
        <!-- Mode édition inline -->
        <template v-if="editingId === session.id">
          <input
            :id="'session-edit-input-' + session.id"
            v-model="editingName"
            class="session-name-input"
            @keydown="handleEditKeydown($event, session.id)"
            @click.stop
            autofocus
            maxlength="40"
            aria-label="Nom de la session"
          />
          <div class="session-edit-actions">
            <button class="icon-btn confirm" @click.stop="confirmEdit(session.id)" title="Valider">
              <Check size="13" />
            </button>
            <button class="icon-btn cancel" @click.stop="cancelEdit()" title="Annuler">
              <X size="13" />
            </button>
          </div>
        </template>

        <!-- Mode confirmation de suppression -->
        <template v-else-if="confirmDeleteId === session.id">
          <span class="delete-confirm-text">Supprimer ?</span>
          <div class="session-edit-actions">
            <button class="icon-btn confirm" @click.stop="confirmDelete(session.id)" title="Oui, supprimer">
              <Check size="13" />
            </button>
            <button class="icon-btn cancel" @click.stop="cancelDelete()" title="Annuler">
              <X size="13" />
            </button>
          </div>
        </template>

        <!-- Mode normal -->
        <template v-else>
          <span class="session-name">{{ session.name }}</span>
          <div class="session-actions">
            <button
              class="icon-btn"
              @click.stop="startEdit(session)"
              title="Renommer"
            >
              <Pencil size="12" />
            </button>
            <button
              class="icon-btn danger"
              @click.stop="askDeleteConfirm(session.id)"
              title="Supprimer"
              :disabled="chatStore.sessions.length <= 1"
            >
              <Trash2 size="12" />
            </button>
          </div>
        </template>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.session-panel {
  width: 210px;
  min-width: 210px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e2e8f0;
  background: #f8fafc;
  border-radius: 24px 0 0 24px;
  overflow: hidden;
}

/* ── Header ── */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.9rem 0.75rem 0.6rem;
  border-bottom: 1px solid #e2e8f0;
  background: white;
  flex-shrink: 0;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 700;
  color: #475569;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.session-count {
  background: #e2e8f0;
  color: #64748b;
  font-size: 0.68rem;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
  letter-spacing: 0.02em;
}

.session-count.at-limit {
  background: rgba(227, 25, 55, 0.1);
  color: var(--zenika-red, #e31937);
}

.new-session-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  border: 1.5px solid #e2e8f0;
  background: white;
  color: #475569;
  cursor: pointer;
  transition: all 0.18s;
  flex-shrink: 0;
}

.new-session-btn:hover:not(:disabled) {
  border-color: var(--zenika-red, #e31937);
  color: var(--zenika-red, #e31937);
  background: rgba(227, 25, 55, 0.04);
}

.new-session-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── List ── */
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0.5rem 0.6rem;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
  min-height: 38px;
  position: relative;
}

.session-item:hover {
  background: #edf2f7;
}

.session-item.active {
  background: rgba(227, 25, 55, 0.07);
  border-left: 3px solid var(--zenika-red, #e31937);
  padding-left: calc(0.6rem - 3px);
}

.session-name {
  flex: 1;
  font-size: 0.82rem;
  font-weight: 500;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

.session-item.active .session-name {
  color: var(--zenika-red, #e31937);
  font-weight: 600;
}

/* Actions (crayon + poubelle) — masquées par défaut, visibles au hover */
.session-actions {
  display: none;
  gap: 2px;
  flex-shrink: 0;
}

.session-item:hover .session-actions {
  display: flex;
}

/* ── Icon buttons ── */
.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.icon-btn:hover {
  background: #e2e8f0;
  color: #475569;
}

.icon-btn.danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.icon-btn.confirm:hover {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.icon-btn.cancel:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.icon-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* ── Edit mode ── */
.session-name-input {
  flex: 1;
  font-size: 0.82rem;
  font-weight: 500;
  color: #334155;
  border: 1.5px solid var(--zenika-red, #e31937);
  border-radius: 6px;
  padding: 2px 6px;
  background: white;
  outline: none;
  min-width: 0;
}

/* Compensation focus clavier WCAG 2.1 AA */
.session-name-input:focus-visible {
  box-shadow: 0 0 0 3px rgba(227, 25, 55, 0.25);
}

.session-edit-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

/* ── Delete confirm ── */
.delete-confirm-text {
  flex: 1;
  font-size: 0.78rem;
  font-weight: 600;
  color: #ef4444;
  white-space: nowrap;
}
</style>
