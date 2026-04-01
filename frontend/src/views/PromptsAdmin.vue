<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'


const prompts = ref<any[]>([])
const originalPrompts = ref<Record<string, string>>({})
const loading = ref(true)
const error = ref('')
const success = ref('')

const analyzingKey = ref<string | null>(null)
const analysisResult = ref<{key: string, data: any} | null>(null)
const showModal = ref(false)

const analyzePrompt = async (prompt: any) => {
  try {
    analyzingKey.value = prompt.key
    error.value = ''
    const res = await axios.post(`/prompts-api/prompts/${prompt.key}/analyze`)
    analysisResult.value = { key: prompt.key, data: res.data }
    showModal.value = true
  } catch(e: any) {
    error.value = "Erreur de l'analyse: " + (e.response?.data?.detail || e.message)
  } finally {
    analyzingKey.value = null
  }
}

const acceptImprovedPrompt = async () => {
   if (!analysisResult.value) return;
   const target = prompts.value.find(p => p.key === analysisResult.value!.key)
   if (target) {
       target.value = analysisResult.value.data.improved_prompt
       await updatePrompt(target)
   }
   showModal.value = false
}

const closeModal = () => {
    showModal.value = false
    analysisResult.value = null
}

const fetchPrompts = async () => {
  try {
    loading.value = true
    error.value = ''
    const res = await axios.get('/prompts-api/prompts/')
    prompts.value = res.data
    res.data.forEach((p: any) => {
      originalPrompts.value[p.key] = p.value
    })
  } catch(e: any) {
    error.value = "Erreur lors de la récupération des prompts: " + e.message
  } finally {
    loading.value = false
  }
}

const updatePrompt = async (prompt: any) => {
  try {
    error.value = ''
    success.value = ''
    const res = await axios.put(`/prompts-api/prompts/${prompt.key}`, {
      value: prompt.value
    })
    success.value = "Prompt mis à jour avec succès : " + res.data.key
    originalPrompts.value[prompt.key] = res.data.value
    setTimeout(() => success.value = '', 3000)
  } catch(e: any) {
    error.value = "Erreur lors de la mise à jour: " + e.message
  }
}

onMounted(() => {
  fetchPrompts()
})
</script>

<template>
  <div class="prompts-admin">
    <h1 class="page-title">Administration des AI Prompts</h1>
    <p class="subtitle">Gestion dynamique des directives du Modèle Gemini</p>

    <div v-if="error" class="alert error">{{ error }}</div>
    <div v-if="success" class="alert success">{{ success }}</div>

    <div v-if="loading" class="loading">Chargement des instructions depuis le réseau...</div>
    
    <div v-else class="prompts-list">
      <div v-for="prompt in prompts" :key="prompt.key" class="prompt-card">
        <h3 class="prompt-key">{{ prompt.key }}</h3>
        <p class="updated-at">Dernière modification : <span v-if="prompt.updated_at">{{ new Date(prompt.updated_at).toLocaleString() }}</span></p>
        
        <textarea 
          v-model="prompt.value" 
          rows="15" 
          class="prompt-textarea" 
          placeholder="Instructions pour le Modèle IA..."
        ></textarea>
        <div class="actions">
          <button class="btn secondary" @click="analyzePrompt(prompt)" :disabled="analyzingKey === prompt.key">
            {{ analyzingKey === prompt.key ? 'Analyse en cours...' : '✨ Improve Prompt' }}
          </button>
          <button 
            class="btn primary" 
            @click="updatePrompt(prompt)"
            :disabled="originalPrompts[prompt.key] === prompt.value"
          >
            Enregistrer la modification
          </button>
        </div>
      </div>
      <div v-if="prompts.length === 0" class="empty-state">
        Aucun prompt trouvé. Avez-vous exécuté le Seeder Backend ?
      </div>
    </div>

    <!-- Modal -->
    <div v-if="showModal && analysisResult" class="modal-overlay">
      <div class="modal">
        <h2>Rapport d'Analyse (Promptfoo & Gemini)</h2>
        
        <div class="report-section">
            <h4>Rapport Promptfoo (Évaluation):</h4>
            <div class="report-code">
               <pre>{{ JSON.stringify(analysisResult.data.promptfoo_report, null, 2) }}</pre>
            </div>
        </div>

        <div class="report-section">
            <h4>Nouveau Prompt Suggéré:</h4>
            <textarea readonly rows="8" class="prompt-textarea">{{ analysisResult.data.improved_prompt }}</textarea>
        </div>
        
        <div class="modal-actions">
           <button class="btn ghost" @click="closeModal">Annuler</button>
           <button class="btn primary" @click="acceptImprovedPrompt">Remplacer par la suggestion</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.prompts-admin {
  padding: 2rem;
  max-width: 1000px;
  margin: 0 auto;
}

.page-title {
  color: var(--zenika-red);
  margin-bottom: 0.5rem;
}

.subtitle {
  color: var(--text-secondary);
  margin-bottom: 2rem;
}

.alert {
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.5rem;
  font-weight: 500;
}

.alert.error {
  background: rgba(227, 25, 55, 0.1);
  color: #ff4d4f;
  border: 1px solid rgba(227, 25, 55, 0.2);
}

.alert.success {
  background: rgba(46, 204, 113, 0.1);
  color: #2ecc71;
  border: 1px solid rgba(46, 204, 113, 0.2);
}

.prompts-list {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.prompt-card {
  background: var(--surface-light);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 1.5rem;
  backdrop-filter: blur(10px);
}

.prompt-key {
  font-size: 1.25rem;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
  font-family: monospace;
}

.updated-at {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 1rem;
}

.prompt-textarea {
  width: 100%;
  background: #1A1A1A;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #f8f8f2;
  border-radius: 8px;
  padding: 1.2rem;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.95rem;
  line-height: 1.5;
  resize: vertical;
  margin-bottom: 1rem;
  transition: all 0.3s ease;
  box-shadow: inset 0 4px 12px rgba(0, 0, 0, 0.5);
}

.prompt-textarea:focus {
  outline: none;
  border-color: var(--zenika-red);
  box-shadow: inset 0 4px 12px rgba(0, 0, 0, 0.5), 0 0 0 3px rgba(227, 25, 55, 0.25);
}

.btn {
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  border: none;
}

.btn.primary {
  background: var(--zenika-red);
  color: white;
}

.btn.primary:disabled {
  background: var(--text-secondary);
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.btn.primary:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: translateY(-1px);
}

.update-btn {
  display: block;
  margin-left: auto;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
}

.btn.secondary {
  background: white;
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn.secondary:hover:not(:disabled) {
  border-color: var(--zenika-red);
  color: var(--zenika-red);
}

.btn.secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn.ghost {
  background: transparent;
  color: var(--text-secondary);
}
.btn.ghost:hover {
  background: rgba(0,0,0,0.05);
}

.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 12px;
  padding: 2rem;
  width: 90%;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 10px 40px rgba(0,0,0,0.2);
}

.modal h2 {
  margin-bottom: 1.5rem;
  color: var(--zenika-red);
}

.report-section {
  margin-bottom: 1.5rem;
}

.report-section h4 {
  margin-bottom: 0.5rem;
  color: var(--text-primary);
}

.report-code {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 1rem;
  border-radius: 8px;
  max-height: 200px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 0.85rem;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  margin-top: 2rem;
}

.loading, .empty-state {
  text-align: center;
  padding: 3rem;
  color: var(--text-secondary);
  background: var(--surface-light);
  border-radius: 12px;
  border: 1px solid var(--border-color);
}
</style>
