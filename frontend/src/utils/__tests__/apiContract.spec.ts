/**
 * apiContract.spec.ts — Tests Vitest pour parsePaginated et ContractError.
 *
 * Ces tests garantissent que le helper détecte correctement les ruptures
 * de contrat API (ex : 'missions' au lieu de 'items').
 */
import { describe, it, expect, vi } from 'vitest';
import { parsePaginated, parsePaginatedItems, ContractError } from '../apiContract';

// ── Helpers ──────────────────────────────────────────────────────────────────

interface Mission {
  id: number;
  title: string;
}

// ── Tests principaux ──────────────────────────────────────────────────────────

describe('parsePaginated', () => {
  describe('Cas valides', () => {
    it('accepte un format paginé complet', () => {
      const data = { items: [{ id: 1, title: 'Mission A' }], total: 1, skip: 0, limit: 50 };
      const result = parsePaginated<Mission>(data, 'missions', '/user/1/missions');
      expect(result.items).toHaveLength(1);
      expect(result.items[0].title).toBe('Mission A');
      expect(result.total).toBe(1);
    });

    it('accepte une liste vide', () => {
      const data = { items: [], total: 0 };
      const result = parsePaginated<Mission>(data, 'missions', '/user/1/missions');
      expect(result.items).toEqual([]);
      expect(result.total).toBe(0);
    });

    it('infère total depuis items.length si total absent', () => {
      const data = { items: [{ id: 1, title: 'M1' }, { id: 2, title: 'M2' }] };
      const result = parsePaginated<Mission>(data, 'missions', '/user/1/missions');
      expect(result.total).toBe(2);
    });

    it('applique des valeurs par défaut pour skip et limit', () => {
      const data = { items: [], total: 0 };
      const result = parsePaginated<Mission>(data, 'missions', '/user/1/missions');
      expect(result.skip).toBe(0);
      expect(result.limit).toBe(50);
    });
  });

  describe('Ruptures de contrat — mode dégradé (throwOnError=false)', () => {
    it('retourne vide si items est absent et log une erreur', () => {
      // Régression critique : ancienne clé 'missions' au lieu de 'items'
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const data = { missions: [{ id: 1, title: 'Mission A' }], total: 1 };
      const result = parsePaginated<Mission>(data, 'missions', '/user/1/missions');
      expect(result.items).toEqual([]);
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('[ContractError]'),
        expect.anything(),
      );
      consoleSpy.mockRestore();
    });

    it('retourne vide si la réponse est null', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const result = parsePaginated<Mission>(null, 'missions', '/user/1/missions');
      expect(result.items).toEqual([]);
      consoleSpy.mockRestore();
    });

    it('retourne vide si la réponse est une string', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const result = parsePaginated<Mission>('bad response', 'missions', '/user/1/missions');
      expect(result.items).toEqual([]);
      consoleSpy.mockRestore();
    });

    it("retourne vide si 'items' n'est pas un tableau", () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const data = { items: 'not-an-array', total: 0 };
      const result = parsePaginated<Mission>(data, 'missions', '/user/1/missions');
      expect(result.items).toEqual([]);
      consoleSpy.mockRestore();
    });

    it('inclut les clés reçues dans le log pour diagnostic', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const data = { users: [], total: 0 };  // mauvaise clé
      parsePaginated<Mission>(data, 'missions', '/user/1/missions');
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('users'),
        expect.anything(),
      );
      consoleSpy.mockRestore();
    });
  });

  describe('Mode strict (throwOnError=true)', () => {
    it('lève ContractError si items est absent', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const data = { missions: [], total: 0 };
      expect(() => parsePaginated<Mission>(data, 'missions', '/user/1/missions', true))
        .toThrowError(ContractError);
      consoleSpy.mockRestore();
    });

    it('lève ContractError si la réponse est null', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      expect(() => parsePaginated<Mission>(null, 'test', '/test', true))
        .toThrowError(ContractError);
      consoleSpy.mockRestore();
    });

    it('ContractError contient le context et l\'endpoint', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      try {
        parsePaginated<Mission>({ bad: [] }, 'missions', '/user/1/missions', true);
      } catch (e) {
        expect(e).toBeInstanceOf(ContractError);
        const err = e as ContractError;
        expect(err.context).toBe('missions');
        expect(err.endpoint).toBe('/user/1/missions');
      }
      consoleSpy.mockRestore();
    });
  });
});

// ── parsePaginatedItems ───────────────────────────────────────────────────────

describe('parsePaginatedItems', () => {
  it('retourne le tableau d\'items directement', () => {
    const data = { items: [{ id: 1, title: 'M1' }], total: 1 };
    const items = parsePaginatedItems<Mission>(data, 'missions', '/user/1/missions');
    expect(items).toHaveLength(1);
    expect(items[0].id).toBe(1);
  });

  it('retourne [] sur rupture de contrat', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const items = parsePaginatedItems<Mission>({ missions: [] }, 'missions', '/test');
    expect(items).toEqual([]);
    consoleSpy.mockRestore();
  });
});
