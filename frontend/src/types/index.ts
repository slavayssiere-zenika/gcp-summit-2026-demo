export interface User {
  id?: number
  user_id?: number
  email: string
  username?: string
  full_name?: string
  is_active?: boolean
  role?: string
}

export interface Item {
  name: string
  categories?: any
  owner?: string | number
  user_id?: number
  description?: string
}

export interface CompetencyNode {
  id?: number | string
  name?: string
  parent_id?: number | string
  sub_competencies?: CompetencyNode[]
  [key: string]: any // allow other dynamic keys
}

export interface Pagination {
  currentPage: number
  itemsPerPage: number
}

export interface Usage {
  total_input_tokens: number
  total_output_tokens: number
  estimated_cost_usd: number
}

export interface AgentStep {
  type: 'call' | 'result' | 'warning' | 'cache'
  tool?: string
  args?: Record<string, any>
  data?: any
  source?: string
}

/** @deprecated Use AgentStep instead */
export interface Step {
  type: string
  tool?: string
  args?: Record<string, any>
  data?: any
}

export interface Message {
  role: 'user' | 'assistant' | 'error'
  content: string
  data?: any // Raw original tool data
  parsedData?: any[] // Formatted or treeified data
  displayType?: string // 'text_only', 'cards', 'table', 'tree', 'cloudrun_logs'
  typing?: boolean

  // Expert Mode & History fields
  steps?: AgentStep[]
  thoughts?: string
  rawResponse?: string
  activeTab?: 'preview' | 'expert'

  // Prompt de débogage extrait du markdown de l'agent ops
  debugPrompt?: string

  // Controls
  pagination?: Pagination
  usage?: Usage
  // ADR12-4 — Semantic cache metadata
  semanticCacheHit?: boolean
  // Résultats sémantiques extraits des steps (search_candidates_multi_criteria)
  // Permet l'affichage dual : table évaluations + cards consultants
  consultantCards?: any[]
}

/**
 * Contrat de réponse du endpoint POST /query.
 * Miroir TypeScript du schema Pydantic AgentQueryResponse (agent_commons/schemas.py).
 * Toute modification de ce type est un breaking change — mettre à jour les deux fichiers.
 *
 * @see agent_commons/agent_commons/schemas.py#AgentQueryResponse
 */
export interface AgentQueryResponse {
  /** Réponse textuelle de l'agent en langage naturel (Markdown). */
  response: string
  /** Chaîne de pensée Gemini (Thinking mode) — vide string si désactivé. */
  thoughts: string
  /** Données structurées pour les UI cards (consultants, missions, etc.). Null si texte uniquement. */
  data: any | null
  /** Hint UI sémantique (ex: 'consultants', 'missions'). Null = affichage texte. */
  display_type: string | null
  /** Trace d'exécution des tools (mode Expert). */
  steps: AgentStep[]
  /** Source de la réponse : 'adk_agent' | 'semantic_cache' | 'error'. */
  source: string
  /** Session ADK utilisée pour ce tour de conversation. */
  session_id: string | null
  /** Consommation tokens FinOps. */
  usage: Usage
  /** Score de confiance [0.0–1.0]. Null si mode dégradé. */
  confidence: number | null
  /** True si la réponse a été servie depuis le cache sémantique. */
  semantic_cache_hit: boolean | null
  /** True si un sous-agent a répondu en mode dégradé (circuit-breaker ouvert). */
  degraded: boolean | null
}
