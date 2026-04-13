import type { CompetencyNode } from '@/types'

export const treeify = (items: CompetencyNode[]): CompetencyNode[] => {
  if (!items || !Array.isArray(items)) return [];
  const map: Record<string | number, CompetencyNode> = {};
  const roots: CompetencyNode[] = [];
  
  // Clone and initialize
  items.forEach(item => {
    if (item && typeof item === 'object') {
      map[item.id!] = { ...item, sub_competencies: [] };
    }
  });
  
  // Link parents and children
  items.forEach(item => {
    if (item && typeof item === 'object') {
      const node = map[item.id!];
      if (item.parent_id && map[item.parent_id]) {
        map[item.parent_id].sub_competencies!.push(node);
      } else {
        roots.push(node);
      }
    }
  });
  return roots;
}
