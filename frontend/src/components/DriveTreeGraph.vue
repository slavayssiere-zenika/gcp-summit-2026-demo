<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import axios from 'axios'
import { authService } from '../services/auth'
import { Folder, File, AlertCircle, ChevronRight, ChevronDown, CheckCircle2, User, Loader2, Network, Search, X } from 'lucide-vue-next'

const folders = ref<any[]>([])
const files = ref<any[]>([])
const isLoading = ref(true)

const fetchTree = async () => {
    isLoading.value = true
    try {
        const headers = { Authorization: `Bearer ${authService.state.token}` }
        
        // 1. Fetch folders
        const fRes = await axios.get('/api/drive/folders', { headers })
        folders.value = fRes.data
        
        // 2. Fetch all files using pagination
        let allFiles: any[] = []
        let skip = 0
        const limit = 500
        
        while (true) {
            const docsRes = await axios.get(`/api/drive/files?skip=${skip}&limit=${limit}`, { headers })
            const data = docsRes.data.files || (Array.isArray(docsRes.data) ? docsRes.data : [])
            allFiles = allFiles.concat(data)
            
            if (data.length < limit || (docsRes.data.total && allFiles.length >= docsRes.data.total)) {
                break
            }
            skip += limit
        }
        
        files.value = allFiles
    } catch(e) {
        console.error(e)
    } finally {
        isLoading.value = false
    }
}

const tree = computed(() => {
    const agencies: Record<string, any> = {}
    
    // Initialiser les dossiers cibles
    for (const f of folders.value) {
        const tag = f.tag || 'Inconnue'
        if (!agencies[tag]) agencies[tag] = { name: tag, folders: {} }
        
        const fname = f.folder_name || f.google_folder_id
        if (!agencies[tag].folders[f.id]) {
            agencies[tag].folders[f.id] = { id: f.id, name: fname, consultants: {} }
        }
    }
    
    // Rattacher les fichiers
    for (const file of files.value) {
        if (!file.folder_id) continue
        
        let agencyFolder = null
        for (const tag in agencies) {
            if (agencies[tag].folders[file.folder_id]) {
                agencyFolder = agencies[tag].folders[file.folder_id]
                break
            }
        }
        
        if (agencyFolder) {
            const consultant = file.parent_folder_name || 'Dossier Inconnu'
            // Heuristique simple: un prénom et un nom séparés par un espace
            const hasNommageError = !consultant.includes(' ') && consultant !== 'Dossier Inconnu'
            
            if (!agencyFolder.consultants[consultant]) {
                agencyFolder.consultants[consultant] = { 
                    name: consultant, 
                    files: [], 
                    hasNommageError,
                    hasErrors: false
                }
            }
            
            agencyFolder.consultants[consultant].files.push(file)
            if (file.status === 'ERROR') {
                agencyFolder.consultants[consultant].hasErrors = true
            }
        }
    }
    
    return agencies
})

const expandedNodes = ref(new Set<string>())
const toggleNode = (id: string) => {
    const newSet = new Set(expandedNodes.value)
    if (newSet.has(id)) newSet.delete(id)
    else newSet.add(id)
    expandedNodes.value = newSet
}

const expandAllErrorNodes = () => {
    const newSet = new Set(expandedNodes.value)
    for (const tag in tree.value) {
        let hasAgencyError = false
        for (const fid in tree.value[tag].folders) {
            let hasFolderError = false
            for (const cname in tree.value[tag].folders[fid].consultants) {
                const cons = tree.value[tag].folders[fid].consultants[cname]
                if (cons.hasNommageError || cons.hasErrors) {
                    newSet.add(`cons_${fid}_${cname}`)
                    hasFolderError = true
                }
            }
            if (hasFolderError) {
                newSet.add(`folder_${fid}`)
                hasAgencyError = true
            }
        }
        if (hasAgencyError) {
            newSet.add(`agency_${tag}`)
        }
    }
    expandedNodes.value = newSet
}

const searchQuery = ref('')

// Arbre filtré par la recherche
const filteredTree = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return tree.value

    const result: Record<string, any> = {}
    for (const tag in tree.value) {
        const agency = tree.value[tag]
        const filteredFolders: Record<string, any> = {}
        for (const fid in agency.folders) {
            const folder = agency.folders[fid]
            const filteredConsultants: Record<string, any> = {}
            for (const cname in folder.consultants) {
                if (cname.toLowerCase().includes(q)) {
                    filteredConsultants[cname] = folder.consultants[cname]
                }
            }
            if (Object.keys(filteredConsultants).length > 0) {
                filteredFolders[fid] = { ...folder, consultants: filteredConsultants }
            }
        }
        if (Object.keys(filteredFolders).length > 0) {
            result[tag] = { ...agency, folders: filteredFolders }
        }
    }
    return result
})

const searchResultCount = computed(() => {
    let count = 0
    for (const tag in filteredTree.value) {
        for (const fid in filteredTree.value[tag].folders) {
            count += Object.keys(filteredTree.value[tag].folders[fid].consultants).length
        }
    }
    return count
})

// Auto-déplier les résultats quand la recherche change
watch(searchQuery, (q) => {
    if (!q.trim()) return
    const newSet = new Set(expandedNodes.value)
    for (const tag in filteredTree.value) {
        newSet.add(`agency_${tag}`)
        for (const fid in filteredTree.value[tag].folders) {
            newSet.add(`folder_${fid}`)
        }
    }
    expandedNodes.value = newSet
})

onMounted(async () => {
    await fetchTree()
    expandAllErrorNodes()
})

// Helper : découpe le nom en segments match/non-match pour le surlignage
const highlightName = (name: string, query: string): { text: string, match: boolean }[] => {
    if (!query) return [{ text: name, match: false }]
    const q = query.toLowerCase()
    const parts: { text: string, match: boolean }[] = []
    let i = 0
    while (i < name.length) {
        const idx = name.toLowerCase().indexOf(q, i)
        if (idx === -1) {
            parts.push({ text: name.slice(i), match: false })
            break
        }
        if (idx > i) parts.push({ text: name.slice(i, idx), match: false })
        parts.push({ text: name.slice(idx, idx + q.length), match: true })
        i = idx + q.length
    }
    return parts
}
</script>

<template>
  <div class="card tree-card">
    <div class="section-header-flex">
      <h3 style="display:flex; align-items:center; gap:8px;">
        <Network class="icon-sm" style="color: var(--zenika-red)" /> 
        Graphe d'Ingestion & Diagnostics
      </h3>
      <div style="display:flex; gap: 8px;">
        <button class="btn-secondary btn-sm" @click="expandAllErrorNodes" :disabled="isLoading">
          <AlertCircle class="icon-sm text-danger" /> Voir problèmes
        </button>
        <button class="btn-secondary btn-sm" @click="fetchTree" :disabled="isLoading">
          <Loader2 v-if="isLoading" class="icon-sm spin" /> 
          <span v-else>Rafraîchir</span>
        </button>
      </div>
    </div>

    <!-- Barre de recherche consultant -->
    <div class="search-bar-wrapper">
      <Search class="search-icon" />
      <input
        id="drive-tree-search"
        v-model="searchQuery"
        type="text"
        class="search-input"
        placeholder="Rechercher un consultant..."
        autocomplete="off"
      />
      <span v-if="searchQuery" class="search-count">
        {{ searchResultCount }} résultat{{ searchResultCount !== 1 ? 's' : '' }}
      </span>
      <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''" title="Effacer">
        <X class="icon-sm" />
      </button>
    </div>

    <div v-if="isLoading" class="loading-state">
      <Loader2 class="icon-lg spin text-muted" />
      <p>Chargement de l'arborescence...</p>
    </div>
    
    <div v-else class="tree-container">
      <div v-if="Object.keys(filteredTree).length === 0 && searchQuery" class="text-muted text-center" style="padding: 2rem;">
        <Search style="width:32px;height:32px;margin:0 auto 0.5rem;display:block;color:#cbd5e1" />
        Aucun consultant trouvé pour "{{ searchQuery }}"
      </div>
      <div v-else-if="Object.keys(filteredTree).length === 0" class="text-muted text-center" style="padding: 2rem;">
        Aucune donnée disponible.
      </div>
      
      <div v-for="(agency, tag) in filteredTree" :key="tag" class="tree-node">
        <div class="node-header" @click="toggleNode('agency_'+tag)">
          <component :is="expandedNodes.has('agency_'+tag) ? ChevronDown : ChevronRight" class="tree-toggle" />
          <div class="node-content agency-node">
            <Folder class="icon-sm text-blue" />
            <span class="node-label">Agence: {{ tag }}</span>
          </div>
        </div>
        
        <div v-if="expandedNodes.has('agency_'+tag)" class="node-children">
          <div v-for="(folder, fid) in agency.folders" :key="fid" class="tree-node">
            <div class="node-header" @click="toggleNode('folder_'+fid)">
              <component :is="expandedNodes.has('folder_'+fid) ? ChevronDown : ChevronRight" class="tree-toggle" />
              <div class="node-content target-node">
                <Folder class="icon-sm text-purple" />
                <span class="node-label">{{ folder.name }}</span>
                <span class="node-count">({{ Object.keys(folder.consultants).length }} dossiers)</span>
              </div>
            </div>
            
            <div v-if="expandedNodes.has('folder_'+fid)" class="node-children">
              <div v-for="(consultant, cname) in folder.consultants" :key="cname" class="tree-node">
                <div class="node-header" @click="toggleNode('cons_'+fid+'_'+cname)">
                  <component :is="expandedNodes.has('cons_'+fid+'_'+cname) ? ChevronDown : ChevronRight" class="tree-toggle" />
                  <div class="node-content consultant-node" :class="{'has-error': consultant.hasNommageError || consultant.hasErrors}">
                    <User class="icon-sm" :class="consultant.hasNommageError ? 'text-danger' : 'text-gray'" />
                    <span class="node-label" :class="{'text-danger fw-bold': consultant.hasNommageError}">
                      <!-- Highlight du terme recherché -->
                      <template v-if="searchQuery">
                        <span v-for="(part, i) in highlightName(cname as string, searchQuery)" :key="i"
                          :class="part.match ? 'search-highlight' : ''">{{ part.text }}</span>
                      </template>
                      <template v-else>{{ consultant.name }}</template>
                    </span>
                    <span v-if="consultant.hasNommageError" class="badge-error" title="Le nom du dossier devrait être 'Prénom Nom'">
                      ⚠️ Problème de nommage
                    </span>
                  </div>
                </div>
                
                <div v-if="expandedNodes.has('cons_'+fid+'_'+cname)" class="node-children file-children">
                  <div v-for="file in consultant.files" :key="file.google_file_id" class="leaf-node">
                    <File class="icon-sm text-blue" />
                    <div class="file-info">
                      <span class="file-name">{{ file.file_name }}</span>
                      <div class="file-meta">
                        <span class="status-badge" :class="'status-'+file.status.toLowerCase()">
                          {{ file.status }}
                        </span>
                        <span v-if="file.error_message" class="text-danger file-error-msg" :title="file.error_message">
                          {{ file.error_message.substring(0, 40) }}{{ file.error_message.length > 40 ? '...' : '' }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tree-card {
  margin-top: 1.5rem;
  padding: 1.5rem;
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.03);
}

.section-header-flex {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 1rem;
}

.tree-container {
  font-size: 0.9rem;
  max-height: 600px;
  overflow-y: auto;
  padding-right: 8px;
  border: 1px solid #f1f5f9;
  border-radius: 12px;
  padding: 1rem;
  background: #fafaf9;
}

.tree-node {
  margin-bottom: 2px;
}

.node-header {
  display: flex;
  align-items: center;
  padding: 8px 6px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.node-header:hover {
  background: #f1f5f9;
}

.tree-toggle {
  width: 16px;
  height: 16px;
  color: #94a3b8;
  margin-right: 6px;
  flex-shrink: 0;
}

.node-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.node-content.has-error {
  background: rgba(254, 226, 226, 0.4);
  padding-right: 12px;
  border-radius: 6px;
}

.agency-node .node-label { font-weight: 700; color: #1e293b; font-size: 1rem; }
.target-node .node-label { font-weight: 600; color: #334155; }
.consultant-node .node-label { font-weight: 500; color: #475569; }

.text-blue { color: #3b82f6; }
.text-purple { color: #8b5cf6; }
.text-gray { color: #64748b; }
.text-danger { color: #ef4444; }
.text-muted { color: #94a3b8; }

.node-count {
  font-size: 0.8rem;
  color: #94a3b8;
  margin-left: auto;
}

.badge-error {
  background: #fee2e2;
  color: #ef4444;
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 700;
  margin-left: auto;
  border: 1px solid #fca5a5;
}

.node-children {
  margin-left: 22px;
  border-left: 1px solid #e2e8f0;
  padding-left: 8px;
  padding-top: 2px;
  padding-bottom: 2px;
}

.file-children {
  background: white;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  padding: 8px 12px;
  margin-top: 4px;
  margin-bottom: 8px;
}

.leaf-node {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px dashed #f1f5f9;
}
.leaf-node:last-child { border-bottom: none; padding-bottom: 0; }

.file-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-name {
  font-weight: 500;
  color: #334155;
  font-size: 0.85rem;
  word-break: break-all;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.file-error-msg {
  font-size: 0.75rem;
  font-style: italic;
}

.status-badge {
  font-size: 0.65rem;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.status-imported_cv { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
.status-error { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
.status-pending { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
.status-queued { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
.status-processing { background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe; }
.status-ignored { background: #f3f4f6; color: #6b7280; border: 1px solid #d1d5db; }

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.85rem;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 600;
}

.btn-secondary:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #cbd5e1;
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spin { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  color: #64748b;
  gap: 12px;
}

/* Barre de recherche */
.search-bar-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f8fafc;
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  padding: 6px 12px;
  margin-bottom: 1rem;
  transition: border-color 0.2s;
}
.search-bar-wrapper:focus-within {
  border-color: #6366f1;
  background: white;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
}
.search-icon {
  width: 16px;
  height: 16px;
  color: #94a3b8;
  flex-shrink: 0;
}
.search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 0.875rem;
  color: #334155;
}
.search-input::placeholder { color: #cbd5e1; }
.search-count {
  font-size: 0.75rem;
  color: #6366f1;
  font-weight: 600;
  white-space: nowrap;
}
.search-clear {
  background: none;
  border: none;
  cursor: pointer;
  color: #94a3b8;
  display: flex;
  align-items: center;
  padding: 0;
  transition: color 0.15s;
}
.search-clear:hover { color: #ef4444; }

/* Surlignage du terme recherché */
.search-highlight {
  background: #fef08a;
  color: #713f12;
  border-radius: 2px;
  font-weight: 700;
}
</style>
