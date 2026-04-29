import { describe, it, expect } from 'vitest'
import type { User, Item, CompetencyNode, Usage, Message } from '../index'

describe('Types TypeScript — vérification de structure', () => {
  it('User doit accepter les propriétés optionnelles', () => {
    const user: User = { email: 'alice@zenika.com' }
    expect(user.email).toBe('alice@zenika.com')
    expect(user.role).toBeUndefined()
  })

  it('User doit accepter toutes les propriétés', () => {
    const user: User = {
      id: 1,
      email: 'alice@zenika.com',
      username: 'alice',
      full_name: 'Alice Martin',
      is_active: true,
      role: 'admin'
    }
    expect(user.id).toBe(1)
    expect(user.role).toBe('admin')
  })

  it('Item doit accepter uniquement le nom comme obligatoire', () => {
    const item: Item = { name: 'MacBook Pro' }
    expect(item.name).toBe('MacBook Pro')
    expect(item.description).toBeUndefined()
  })

  it('CompetencyNode doit supporter la récursivité', () => {
    const node: CompetencyNode = {
      id: 1,
      name: 'Root',
      sub_competencies: [
        { id: 2, name: 'Child', sub_competencies: [] }
      ]
    }
    expect(node.sub_competencies![0].name).toBe('Child')
  })

  it('Usage doit calculer correctement les tokens', () => {
    const usage: Usage = {
      total_input_tokens: 1000,
      total_output_tokens: 500,
      estimated_cost_usd: 0.00045
    }
    const total = usage.total_input_tokens + usage.total_output_tokens
    expect(total).toBe(1500)
    expect(usage.estimated_cost_usd).toBeCloseTo(0.00045)
  })

  it('Message doit supporter tous les rôles', () => {
    const userMsg: Message = { role: 'user', content: 'Bonjour' }
    const assistantMsg: Message = {
      role: 'assistant',
      content: 'Voici les résultats',
      displayType: 'cards',
      activeTab: 'preview',
      semanticCacheHit: false,
      pagination: { currentPage: 1, itemsPerPage: 10 }
    }
    expect(userMsg.role).toBe('user')
    expect(assistantMsg.displayType).toBe('cards')
    expect(assistantMsg.pagination?.currentPage).toBe(1)
  })
})
