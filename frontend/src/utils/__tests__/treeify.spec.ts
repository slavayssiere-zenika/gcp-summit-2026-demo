import { describe, it, expect } from 'vitest'
import { treeify } from '../treeify'
import type { CompetencyNode } from '@/types'

describe('treeify', () => {
  it('doit transformer une liste plate en arbre', () => {
    const items: CompetencyNode[] = [
      { id: 1, name: 'Root', parent_id: null },
      { id: 2, name: 'Child 1', parent_id: 1 },
      { id: 3, name: 'Child 2', parent_id: 1 },
      { id: 4, name: 'Grandchild', parent_id: 2 }
    ]
    const tree = treeify(items)
    expect(tree.length).toBe(1)
    expect(tree[0].id).toBe(1)
    expect(tree[0].sub_competencies?.length).toBe(2)
    expect(tree[0].sub_competencies![0].sub_competencies?.length).toBe(1)
  })

  it('doit gérer les tableaux vides ou invalides', () => {
    expect(treeify([])).toEqual([])
    expect(treeify(null as any)).toEqual([])
  })
})
