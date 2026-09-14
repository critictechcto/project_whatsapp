import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo } from 'react'
import { api, apiFetch, unwrap } from '../../../api/client'
import { cursorFromUrl } from '../../../api/pagination'
import { workspaceKeys } from '../../../api/queryKeys'
import { useWorkspace } from '../../../lib/workspace'
import type { ContactImport, Tag } from './lib/types'

/** Every contacts query key starts with `['ws', workspaceId, 'contacts']`. */
export const contactKeys = workspaceKeys('contacts')

export type ContactListFilters = {
  search: string
  tags: string[]
  status: string
}

const MAX_TAG_PAGES = 10

async function fetchAllTags(signal: AbortSignal): Promise<Tag[]> {
  const tags: Tag[] = []
  let cursor: string | undefined
  for (let page = 0; page < MAX_TAG_PAGES; page++) {
    const data = await unwrap(api.GET('/api/v1/contacts/tags/', { params: { query: { page_size: 200, cursor } }, signal }))
    tags.push(...data.results)
    cursor = cursorFromUrl(data.next)
    if (!cursor) break
  }
  return tags.sort((a, b) => a.name.localeCompare(b.name))
}

/** All tags of the workspace, sorted by name, plus an id → tag map. */
export function useTags() {
  const { workspaceId } = useWorkspace()
  const query = useQuery({
    queryKey: contactKeys.custom(workspaceId, 'tags'),
    queryFn: ({ signal }) => fetchAllTags(signal),
  })
  const tags = useMemo(() => query.data ?? [], [query.data])
  const tagMap = useMemo(() => new Map(tags.map((tag) => [tag.id, tag])), [tags])
  return { ...query, tags, tagMap }
}

/** Member user id → display name, used to say who recorded a consent change. */
export function useMemberNames() {
  const { workspaceId } = useWorkspace()
  const query = useQuery({
    queryKey: contactKeys.custom(workspaceId, 'members'),
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/v1/workspaces/members/', { params: { query: { page_size: 200 } }, signal })),
    staleTime: 5 * 60_000,
  })
  return useMemo(
    () => new Map((query.data?.results ?? []).map((member) => [member.user.id, member.user.full_name || member.user.email])),
    [query.data],
  )
}

/** Invalidates every contacts query of the workspace (lists, details, tags, imports). */
export function useInvalidateContacts() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return useCallback(() => queryClient.invalidateQueries({ queryKey: contactKeys.all(workspaceId) }), [queryClient, workspaceId])
}

export type ImportRequest = {
  file: File
  markOptedIn: boolean
  consentAttested: boolean
  optInSource: string
  tagIds: string[]
}

/** `POST /api/v1/contacts/imports/` as multipart (field names from `ContactImportCreateRequest`). */
export function createImport(request: ImportRequest): Promise<ContactImport> {
  const body = new FormData()
  body.append('file', request.file, request.file.name)
  body.append('mark_opted_in', String(request.markOptedIn))
  body.append('consent_attested', String(request.consentAttested))
  if (request.optInSource) body.append('opt_in_source', request.optInSource)
  for (const tagId of request.tagIds) body.append('tag_ids', tagId)
  return apiFetch<ContactImport>('/api/v1/contacts/imports/', { method: 'POST', body })
}

export const importInProgress = (job: Pick<ContactImport, 'status'> | undefined) =>
  job?.status === 'queued' || job?.status === 'processing'
