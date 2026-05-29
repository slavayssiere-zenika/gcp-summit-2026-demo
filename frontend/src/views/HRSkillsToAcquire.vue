<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import {
  BrainCircuit, TrendingUp, RotateCw, CheckCircle2, AlertCircle,
  ChevronDown, ChevronUp, BookOpen, Target, Sparkles, X
} from 'lucide-vue-next'
import { authService } from '../services/auth'
import PageHeader from '../components/ui/PageHeader.vue'

interface LineageItem {
  context: string | null
  occurrence_count: number
  accepted_at: string | null
}

interface SkillToAcquire {
  id: number
  name: string
  description: string | null
  aliases: string | null
  parent_id: number | null
  created_at: string | null
  is_to_acquire: boolean
  total_occurrences: number
  lineage: LineageItem[]
  _expanded?: boolean
}

const skills = ref<SkillToAcquire[]>([])
const isLoading = ref(false)
const error = ref('')
const successMsg = ref('')
const updatingId = ref<number | null>(null)

const sortBy = ref<'occurrences' | 'name'>('occurrences')

const sortedSkills = computed(() => {
  const list = [...skills.value]
  if (sortBy.value === 'occurrences') {
    return list.sort((a, b) => b.total_occurrences - a.total_occurrences)
  }
  return list.sort((a, b) => a.name.localeCompare(b.name))
})

const totalOccurrences = computed(() =>
  skills.value.reduce((sum, s) => sum + s.total_occurrences, 0)
)

const authHeaders = () => ({ Authorization: `Bearer ${authService.state.token}` })

const fetchSkills = async () => {
  isLoading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/competencies/to-acquire', { headers: authHeaders() })
    skills.value = (Array.isArray(res.data) ? res.data : []).map((s: SkillToAcquire) => ({
      ...s,
      _expanded: false
    }))
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Erreur de chargement des compétences à acquérir'
  } finally {
    isLoading.value = false
  }
}

const toggleExpand = (skill: SkillToAcquire) => {
  skill._expanded = !skill._expanded
}

const setToAcquire = async (skill: SkillToAcquire, value: boolean) => {
  updatingId.value = skill.id
  error.value = ''
  successMsg.value = ''
  try {
    await axios.put(
      `/api/competencies/${skill.id}/to-acquire`,
      null,
      { params: { to_acquire: value }, headers: authHeaders() }
    )
    successMsg.value = value
      ? `"${skill.name}" marquée comme compétence clé à acquérir.`
      : `"${skill.name}" retirée des compétences à acquérir.`
    await fetchSkills()
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Erreur lors de la mise à jour.'
  } finally {
    updatingId.value = null
  }
}

const formatDate = (iso: string | null) => {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })
}

onMounted(fetchSkills)
</script>

<template>
  <div class="sta-wrapper fade-in">

    <PageHeader
      title="Compétences clés à acquérir"
      subtitle="Compétences détectées dans les missions clients et absentes du portefeuille Zenika — signal marché prioritaire"
      :icon="BrainCircuit"
      :breadcrumb="[
        { label: 'Hub RH', to: '/admin/availability' },
        { label: 'Compétences à acquérir' }
      ]"
    />

    <!-- KPI Banner -->
    <div class="kpi-row fade-in-up">
      <div class="kpi-card kpi-accent">
        <div class="kpi-icon"><BrainCircuit size="22" /></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ skills.length }}</div>
          <div class="kpi-label">Compétences cibles</div>
        </div>
      </div>
      <div class="kpi-card kpi-teal">
        <div class="kpi-icon kpi-icon-teal"><TrendingUp size="22" /></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ totalOccurrences }}</div>
          <div class="kpi-label">Demandes cumulées (missions)</div>
        </div>
      </div>
      <div class="kpi-card kpi-purple">
        <div class="kpi-icon kpi-icon-purple"><Target size="22" /></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ skills.filter(s => s.total_occurrences >= 3).length }}</div>
          <div class="kpi-label">Priorité haute (≥ 3 mentions)</div>
        </div>
      </div>
    </div>

    <!-- Info Banner -->
    <div class="info-banner fade-in-up">
      <Sparkles size="16" />
      <span>
        Ces compétences ont été <strong>extraites automatiquement de missions clients</strong> et acceptées dans la taxonomie.
        Elles disparaîtront automatiquement de cette liste dès qu'un consultant aura été scoré sur cette compétence (score &gt; 0).
      </span>
    </div>

    <!-- Success / Error -->
    <div v-if="successMsg" class="success-panel fade-in-up">
      <CheckCircle2 size="20" /><span>{{ successMsg }}</span>
    </div>
    <div v-if="error" class="error-panel fade-in-up">
      <AlertCircle size="20" /><span>{{ error }}</span>
    </div>

    <!-- Controls -->
    <div class="controls-row">
      <div class="sort-group">
        <span class="sort-label">Trier par :</span>
        <button
          class="sort-btn"
          :class="{ active: sortBy === 'occurrences' }"
          @click="sortBy = 'occurrences'"
          aria-label="Trier par occurrences"
        >
          <TrendingUp size="13" /> Occurrences
        </button>
        <button
          class="sort-btn"
          :class="{ active: sortBy === 'name' }"
          @click="sortBy = 'name'"
          aria-label="Trier par nom"
        >
          A–Z
        </button>
      </div>
      <button class="refresh-btn" @click="fetchSkills" :disabled="isLoading" aria-label="Rafraîchir la liste">
        <RotateCw size="15" :class="{ spin: isLoading }" />
        Rafraîchir
      </button>
    </div>

    <!-- Loading -->
    <div v-if="isLoading && skills.length === 0" class="loading-state">
      <RotateCw size="40" class="spin" color="#e31937" />
      <p>Chargement des compétences...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="!isLoading && skills.length === 0" class="empty-state fade-in">
      <CheckCircle2 size="56" color="#10b981" />
      <h3>Aucune compétence à acquérir</h3>
      <p>Toutes les compétences demandées en mission sont déjà couvertes par l'équipe Zenika. 🎉</p>
    </div>

    <!-- Skills List -->
    <div v-else class="skills-list">
      <div
        v-for="skill in sortedSkills"
        :key="skill.id"
        class="skill-card fade-in-up"
        :class="{ 'priority-high': skill.total_occurrences >= 3 }"
      >
        <div class="skill-header" @click="toggleExpand(skill)">
          <div class="skill-left">
            <div class="occurrence-badge" :class="skill.total_occurrences >= 3 ? 'badge-hot' : 'badge-normal'">
              <TrendingUp size="11" />
              {{ skill.total_occurrences }} demande{{ skill.total_occurrences > 1 ? 's' : '' }}
            </div>
            <div class="skill-name">{{ skill.name }}</div>
            <div v-if="skill.description" class="skill-desc">{{ skill.description }}</div>
          </div>
          <div class="skill-actions" @click.stop>
            <button
              class="action-clear"
              :disabled="updatingId === skill.id"
              @click="setToAcquire(skill, false)"
              title="Retirer de la liste des compétences à acquérir"
              :aria-label="`Retirer ${skill.name} de la liste`"
            >
              <X size="13" />
              Retirer
            </button>
            <button
              class="expand-btn"
              @click="toggleExpand(skill)"
              :aria-label="skill._expanded ? 'Masquer le lineage' : 'Voir le lineage'"
            >
              <ChevronUp v-if="skill._expanded" size="16" />
              <ChevronDown v-else size="16" />
              Lineage
            </button>
          </div>
        </div>

        <!-- Lineage Panel -->
        <div v-if="skill._expanded" class="lineage-panel">
          <div class="lineage-title">
            <BookOpen size="14" /> Traçabilité — Missions d'origine
          </div>
          <div v-if="skill.lineage.length === 0" class="lineage-empty">
            Aucune trace de suggestion disponible (compétence créée manuellement ou données purgées).
          </div>
          <div v-else class="lineage-table-wrapper">
            <table class="lineage-table">
              <thead>
                <tr>
                  <th>Mission / Contexte</th>
                  <th>Occurrences</th>
                  <th>Date d'acceptation</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, idx) in skill.lineage" :key="idx">
                  <td class="context-cell">{{ item.context || '—' }}</td>
                  <td>
                    <span class="occ-pill">{{ item.occurrence_count }}×</span>
                  </td>
                  <td class="date-cell">{{ formatDate(item.accepted_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="skill.aliases" class="aliases-row">
            <span class="aliases-label">Aliases :</span>
            <span class="aliases-val">{{ skill.aliases }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ── */
.sta-wrapper {
  max-width: 1050px;
  margin: 0 auto;
  padding: 2rem;
}

/* ── KPIs ── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
  margin-bottom: 1.5rem;
}
.kpi-card {
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(20px);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.45);
  padding: 1.25rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
  transition: transform 0.2s;
}
.kpi-card:hover { transform: translateY(-2px); }
.kpi-icon {
  width: 46px; height: 46px; border-radius: 12px;
  background: rgba(227, 25, 55, 0.12);
  color: var(--zenika-red);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.kpi-icon-teal { background: rgba(20, 184, 166, 0.12); color: #0d9488; }
.kpi-icon-purple { background: rgba(124, 58, 237, 0.12); color: #7c3aed; }
.kpi-value { font-size: 2rem; font-weight: 800; color: #0f172a; line-height: 1; }
.kpi-label { font-size: 0.78rem; color: #64748b; margin-top: 4px; font-weight: 500; }

/* ── Info Banner ── */
.info-banner {
  display: flex; align-items: flex-start; gap: 10px;
  background: rgba(99, 102, 241, 0.07);
  border: 1px solid rgba(99, 102, 241, 0.22);
  border-radius: 12px;
  padding: 14px 18px;
  font-size: 0.83rem; color: #3730a3;
  margin-bottom: 1.5rem;
}

/* ── Controls ── */
.controls-row {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 1.25rem;
}
.sort-group { display: flex; align-items: center; gap: 8px; }
.sort-label { font-size: 0.82rem; color: #64748b; }
.sort-btn {
  display: flex; align-items: center; gap: 5px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 8px; padding: 6px 14px;
  font-size: 0.82rem; font-weight: 600; color: #64748b;
  cursor: pointer; transition: all 0.2s;
  backdrop-filter: blur(10px);
}
.sort-btn:hover { background: rgba(255, 255, 255, 0.9); color: #1e293b; }
.sort-btn.active { background: white; color: var(--zenika-red); border-color: rgba(227, 25, 55, 0.25); }

.refresh-btn {
  display: flex; align-items: center; gap: 8px;
  background: white; border: 1px solid #e2e8f0;
  border-radius: 8px; padding: 7px 16px;
  font-size: 0.82rem; font-weight: 600; cursor: pointer;
  transition: all 0.2s; color: #475569;
}
.refresh-btn:hover:not(:disabled) { background: #f8fafc; border-color: #cbd5e1; }
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── States ── */
.loading-state, .empty-state {
  text-align: center; padding: 4rem 2rem; color: #64748b;
}
.loading-state p, .empty-state p { margin-top: 1rem; font-size: 1rem; }
.empty-state h3 { font-size: 1.3rem; font-weight: 700; color: #1e293b; margin: 1rem 0 0.5rem; }

/* ── Skill Cards ── */
.skills-list { display: flex; flex-direction: column; gap: 1rem; }

.skill-card {
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
  transition: box-shadow 0.2s, transform 0.2s;
}
.skill-card:hover { box-shadow: 0 8px 28px rgba(0, 0, 0, 0.08); transform: translateY(-1px); }
.priority-high {
  border-color: rgba(227, 25, 55, 0.25);
  box-shadow: 0 4px 20px rgba(227, 25, 55, 0.08);
}

.skill-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 1.1rem 1.4rem; cursor: pointer;
  gap: 1rem;
}
.skill-left { display: flex; align-items: center; gap: 1rem; flex: 1; min-width: 0; }

.occurrence-badge {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px; border-radius: 20px;
  font-size: 0.75rem; font-weight: 700; flex-shrink: 0;
  white-space: nowrap;
}
.badge-hot { background: rgba(227, 25, 55, 0.12); color: #be123c; border: 1px solid rgba(227, 25, 55, 0.2); }
.badge-normal { background: rgba(100, 116, 139, 0.1); color: #475569; border: 1px solid rgba(100, 116, 139, 0.2); }

.skill-name {
  font-size: 1rem; font-weight: 700; color: #0f172a;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.skill-desc {
  font-size: 0.78rem; color: #64748b;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  flex: 1; min-width: 0;
}

.skill-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

.action-clear {
  display: flex; align-items: center; gap: 6px;
  background: transparent;
  border: 1px solid rgba(100, 116, 139, 0.3);
  border-radius: 8px; padding: 5px 12px;
  font-size: 0.78rem; font-weight: 600; color: #94a3b8;
  cursor: pointer; transition: all 0.2s;
}
.action-clear:hover:not(:disabled) {
  border-color: rgba(227, 25, 55, 0.4); color: var(--zenika-red);
  background: rgba(227, 25, 55, 0.06);
}
.action-clear:disabled { opacity: 0.4; cursor: not-allowed; }

.expand-btn {
  display: flex; align-items: center; gap: 5px;
  background: rgba(99, 102, 241, 0.07);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 8px; padding: 5px 12px;
  font-size: 0.78rem; font-weight: 600; color: #4f46e5;
  cursor: pointer; transition: all 0.2s;
}
.expand-btn:hover { background: rgba(99, 102, 241, 0.14); }

/* ── Lineage Panel ── */
.lineage-panel {
  border-top: 1px solid rgba(99, 102, 241, 0.12);
  background: rgba(248, 250, 252, 0.8);
  padding: 1.1rem 1.4rem;
}
.lineage-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.8rem; font-weight: 700;
  color: #4f46e5; margin-bottom: 0.9rem;
  text-transform: uppercase; letter-spacing: 0.05em;
}
.lineage-empty {
  font-size: 0.82rem; color: #94a3b8; font-style: italic;
}
.lineage-table-wrapper { overflow-x: auto; border-radius: 10px; border: 1px solid #e2e8f0; }
.lineage-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.lineage-table th {
  padding: 8px 14px; text-align: left;
  font-size: 0.7rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: #94a3b8; background: #f8fafc; border-bottom: 1px solid #e2e8f0;
}
.lineage-table td { padding: 9px 14px; border-bottom: 1px solid #f1f5f9; color: #1e293b; }
.lineage-table tr:last-child td { border-bottom: none; }
.lineage-table tr:hover td { background: rgba(99, 102, 241, 0.03); }

.context-cell { font-weight: 500; max-width: 420px; }
.date-cell { color: #64748b; white-space: nowrap; }

.occ-pill {
  background: rgba(227, 25, 55, 0.1); color: #be123c;
  padding: 2px 8px; border-radius: 20px;
  font-size: 0.75rem; font-weight: 700;
}

.aliases-row {
  margin-top: 0.75rem; font-size: 0.78rem;
  display: flex; align-items: center; gap: 8px;
}
.aliases-label { color: #94a3b8; font-weight: 600; }
.aliases-val { color: #475569; font-style: italic; }

/* ── Feedback panels ── */
.success-panel {
  display: flex; align-items: center; gap: 10px;
  background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25);
  padding: 12px 18px; border-radius: 10px; font-size: 0.85rem;
  color: #059669; margin-bottom: 1.25rem;
}
.error-panel {
  display: flex; align-items: center; gap: 10px;
  background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25);
  padding: 12px 18px; border-radius: 10px; font-size: 0.85rem;
  color: #b91c1c; margin-bottom: 1.25rem;
}

/* ── Animations ── */
.fade-in { animation: fadeIn 0.4s ease forwards; }
.fade-in-up { animation: fadeInUp 0.5s ease forwards; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

/* ── Responsive ── */
@media (max-width: 768px) {
  .kpi-row { grid-template-columns: 1fr; }
  .skill-header { flex-direction: column; align-items: flex-start; }
  .skill-left { flex-wrap: wrap; }
  .controls-row { flex-direction: column; gap: 0.75rem; align-items: flex-start; }
}
</style>
