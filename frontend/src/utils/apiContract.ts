/**
 * apiContract.ts — Helpers de validation de contrat API pour le frontend.
 *
 * Principe : toutes les réponses paginées de la plateforme doivent
 * suivre le schema `PaginationResponse<T>` (items, total, skip, limit).
 * Ce module offre des helpers fail-fast qui logguent une erreur de contrat
 * explicite plutôt que de retourner silencieusement un tableau vide.
 *
 * Usage :
 *   const missions = parsePaginated<Mission>(response.data, 'missions', '/user/42/missions');
 *   const users = parsePaginated<User>(response.data, 'users', '/users/');
 */

/** Shape générique d'une réponse paginée. */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip?: number;
  limit?: number;
}

/** Résultat d'un parsePaginated — contient les items et les métadonnées. */
export interface ParsedPage<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

/**
 * Valide et extrait les items d'une réponse paginée.
 *
 * @param data     - Le corps JSON brut de la réponse.
 * @param context  - Label lisible pour le logging (nom de la ressource).
 * @param endpoint - URL ou endpoint pour traçabilité dans les logs.
 * @returns ParsedPage<T> — jamais null/undefined.
 * @throws ContractError en mode strict (si throwOnError = true).
 *
 * @example
 *   const page = parsePaginated<Mission>(res.data, 'missions', '/user/1/missions');
 *   console.log(page.items, page.total);
 */
export function parsePaginated<T>(
  data: unknown,
  context: string,
  endpoint: string,
  throwOnError = false,
): ParsedPage<T> {
  const EMPTY: ParsedPage<T> = { items: [], total: 0, skip: 0, limit: 50 };

  if (!data || typeof data !== 'object') {
    logContractError(context, endpoint, 'Réponse non-objet', data);
    if (throwOnError) throw new ContractError(context, endpoint, 'Réponse non-objet');
    return EMPTY;
  }

  const raw = data as Record<string, unknown>;

  // Vérification de la clé 'items' — rupture de contrat la plus courante
  if (!('items' in raw)) {
    const rawKeys = Object.keys(raw);
    logContractError(
      context,
      endpoint,
      `Clé 'items' absente (clés reçues: ${rawKeys.join(', ')})`,
      data,
    );
    if (throwOnError) {
      throw new ContractError(
        context,
        endpoint,
        `Clé 'items' absente (clés reçues: ${rawKeys.join(', ')})`,
      );
    }
    return EMPTY;
  }

  const items = raw['items'];
  if (!Array.isArray(items)) {
    logContractError(context, endpoint, `'items' n'est pas un tableau (type: ${typeof items})`, data);
    if (throwOnError) throw new ContractError(context, endpoint, "'items' n'est pas un tableau");
    return EMPTY;
  }

  const total = typeof raw['total'] === 'number' ? raw['total'] : items.length;

  return {
    items: items as T[],
    total,
    skip: typeof raw['skip'] === 'number' ? raw['skip'] : 0,
    limit: typeof raw['limit'] === 'number' ? raw['limit'] : 50,
  };
}

/**
 * Variante qui retourne seulement le tableau d'items (rétrocompatibilité).
 * Préférer parsePaginated() pour accéder à total, skip, limit.
 */
export function parsePaginatedItems<T>(
  data: unknown,
  context: string,
  endpoint: string,
): T[] {
  return parsePaginated<T>(data, context, endpoint).items;
}

// ── Logging et erreur de contrat ─────────────────────────────────────────────

function logContractError(
  context: string,
  endpoint: string,
  message: string,
  raw: unknown,
): void {
  console.error(
    `[ContractError] ${context} @ ${endpoint}: ${message}`,
    { raw },
  );
  // En production, on pourrait envoyer un événement à un service de monitoring.
}

export class ContractError extends Error {
  constructor(
    public readonly context: string,
    public readonly endpoint: string,
    message: string,
  ) {
    super(`[ContractError] ${context} @ ${endpoint}: ${message}`);
    this.name = 'ContractError';
  }
}
