import type { QueryClient, QueryKey } from '@tanstack/react-query'

/**
 * Query keys. Everything tenant-scoped starts with `['ws', workspaceId, area, ...]`, so a workspace
 * switch can drop exactly those queries and a realtime reconnect can invalidate one workspace.
 */
export const queryKeys = {
  me: ['me'] as const,
  workspaces: ['workspaces'] as const,
  workspace: (workspaceId: string) => ['ws', workspaceId] as const,
}

/**
 * Per-area key factory. Define once per area:
 *
 * ```ts
 * export const templateKeys = workspaceKeys('templates')
 * useQuery({ queryKey: templateKeys.list(workspaceId, { status }), ... })
 * queryClient.invalidateQueries({ queryKey: templateKeys.all(workspaceId) })
 * ```
 */
export function workspaceKeys<Area extends string>(area: Area) {
  return {
    all: (workspaceId: string) => ['ws', workspaceId, area] as const,
    lists: (workspaceId: string) => ['ws', workspaceId, area, 'list'] as const,
    list: <P extends object>(workspaceId: string, params?: P) =>
      ['ws', workspaceId, area, 'list', params ?? {}] as const,
    details: (workspaceId: string) => ['ws', workspaceId, area, 'detail'] as const,
    detail: (workspaceId: string, id: string) => ['ws', workspaceId, area, 'detail', id] as const,
    /** Anything else scoped to the area, e.g. `keys.custom(ws, 'preview', id)`. */
    custom: (workspaceId: string, ...parts: ReadonlyArray<string | number | object>) =>
      ['ws', workspaceId, area, ...parts] as const,
  }
}

export function isWorkspaceKey(key: QueryKey): boolean {
  return key[0] === 'ws'
}

/** Removes every workspace-scoped query (cancelling in-flight ones). Called on workspace switch. */
export function clearWorkspaceQueries(queryClient: QueryClient) {
  const filters = { predicate: (query: { queryKey: QueryKey }) => isWorkspaceKey(query.queryKey) }
  void queryClient.cancelQueries(filters)
  queryClient.removeQueries(filters)
}
