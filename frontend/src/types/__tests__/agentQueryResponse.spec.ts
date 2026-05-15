/**
 * agentQueryResponse.spec.ts — Tests du contrat TypeScript AgentQueryResponse.
 *
 * Valide que l'interface TypeScript est bien alignée avec le schema Pydantic
 * backend (agent_commons/schemas.py#AgentQueryResponse).
 *
 * Ces tests agissent comme des "contract tests" : si le backend change un
 * champ, les tests TypeScript doivent également être mis à jour (breaking change).
 */

import { describe, it, expect } from 'vitest'
import type { AgentQueryResponse, AgentStep, Usage } from '@/types'

// ── Helper factories ──────────────────────────────────────────────────────────

function makeUsage(overrides?: Partial<Usage>): Usage {
  return {
    total_input_tokens: 0,
    total_output_tokens: 0,
    estimated_cost_usd: 0,
    ...overrides,
  }
}

function makeStep(overrides?: Partial<AgentStep>): AgentStep {
  return {
    type: 'call',
    ...overrides,
  }
}

function makeResponse(overrides?: Partial<AgentQueryResponse>): AgentQueryResponse {
  return {
    response: 'Test response',
    thoughts: '',
    data: null,
    display_type: null,
    steps: [],
    source: 'adk_agent',
    session_id: null,
    usage: makeUsage(),
    confidence: null,
    semantic_cache_hit: null,
    degraded: null,
    ...overrides,
  }
}

// ── Tests du contrat AgentQueryResponse ─────────────────────────────────────

describe('AgentQueryResponse — contract tests', () => {
  it('accepte un payload minimal valide', () => {
    const r = makeResponse()
    expect(r.response).toBe('Test response')
    expect(r.thoughts).toBe('')
    expect(r.steps).toHaveLength(0)
    expect(r.source).toBe('adk_agent')
    expect(r.data).toBeNull()
    expect(r.confidence).toBeNull()
  })

  it('accepte un payload complet avec toutes les propriétés', () => {
    const r = makeResponse({
      response: 'J\'ai trouvé 3 consultants.',
      thoughts: 'Je dois chercher les profils...',
      data: { items: [{ id: 1, name: 'Alice Martin' }] },
      display_type: 'consultants',
      steps: [makeStep({ tool: 'ask_hr_agent' })],
      source: 'adk_agent',
      session_id: 'alice@zenika.com',
      usage: makeUsage({ total_input_tokens: 800, total_output_tokens: 200, estimated_cost_usd: 0.00012 }),
      confidence: 0.9,
      semantic_cache_hit: false,
      degraded: false,
    })

    expect(r.response).toContain('consultants')
    expect(r.display_type).toBe('consultants')
    expect(r.confidence).toBe(0.9)
    expect(r.semantic_cache_hit).toBe(false)
    expect(r.degraded).toBe(false)
    expect(r.steps).toHaveLength(1)
    expect(r.steps[0].tool).toBe('ask_hr_agent')
  })

  it('modélise un payload de mode dégradé (circuit-breaker)', () => {
    const r = makeResponse({
      response: '❌ Le sous-agent est temporairement indisponible.',
      degraded: true,
      source: 'error',
    })
    expect(r.degraded).toBe(true)
    expect(r.source).toBe('error')
  })

  it('modélise un payload depuis le cache sémantique', () => {
    const r = makeResponse({
      response: 'Réponse depuis le cache.',
      source: 'semantic_cache',
      semantic_cache_hit: true,
    })
    expect(r.semantic_cache_hit).toBe(true)
    expect(r.source).toBe('semantic_cache')
  })
})

// ── Tests du contrat AgentStep ────────────────────────────────────────────────

describe('AgentStep — contract tests', () => {
  it('accepte tous les types de steps valides', () => {
    const types: Array<AgentStep['type']> = ['call', 'result', 'warning', 'cache']
    types.forEach(type => {
      const step = makeStep({ type })
      expect(step.type).toBe(type)
    })
  })

  it('step call avec outil et arguments', () => {
    const step = makeStep({
      type: 'call',
      tool: 'search_candidates_multi_criteria',
      args: { skills: ['Python', 'GCP'], availability: true },
    })
    expect(step.tool).toBe('search_candidates_multi_criteria')
    expect(step.args?.skills).toContain('Python')
  })

  it('step warning de guardrail', () => {
    const step = makeStep({
      type: 'warning',
      tool: 'GUARDRAIL_HALLUCINATION',
      args: { message: 'Réponse non fondée sur des données réelles.' },
    })
    expect(step.type).toBe('warning')
    expect(step.tool).toBe('GUARDRAIL_HALLUCINATION')
  })

  it('step cache avec source A2A', () => {
    const step = makeStep({
      type: 'cache',
      tool: 'semantic_cache',
      source: 'hr_agent',
    })
    expect(step.source).toBe('hr_agent')
  })
})

// ── Tests du contrat Usage ────────────────────────────────────────────────────

describe('Usage — contract tests', () => {
  it('valeurs par défaut sont toutes à zéro', () => {
    const u = makeUsage()
    expect(u.total_input_tokens).toBe(0)
    expect(u.total_output_tokens).toBe(0)
    expect(u.estimated_cost_usd).toBe(0)
  })

  it('calcule un coût estimé non-nul', () => {
    const u = makeUsage({
      total_input_tokens: 1500,
      total_output_tokens: 300,
      estimated_cost_usd: 1500 * 0.000000075 + 300 * 0.0000003,
    })
    expect(u.estimated_cost_usd).toBeCloseTo(0.0001125 + 0.00009, 8)
  })
})
