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
  steps?: Step[]
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
