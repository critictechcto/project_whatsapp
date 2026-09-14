import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../../api/client'
import { templateKeys } from '../../../../components/app'
import { campaignKeys } from '../api'

export function useTemplate(workspaceId: string, id: string | undefined) {
  return useQuery({
    queryKey: templateKeys.detail(workspaceId, id ?? ''),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/templates/{id}/', { params: { path: { id: id ?? '' } }, signal })),
    enabled: Boolean(id),
  })
}

export function useTagOptions(workspaceId: string) {
  return useQuery({
    queryKey: campaignKeys.custom(workspaceId, 'tag-options'),
    queryFn: async ({ signal }) =>
      (await unwrap(api.GET('/api/v1/contacts/tags/', { params: { query: { page_size: 200 } }, signal }))).results,
    staleTime: 60_000,
  })
}

export function useContactOptions(workspaceId: string, search: string) {
  return useQuery({
    queryKey: campaignKeys.custom(workspaceId, 'contact-options', search),
    queryFn: async ({ signal }) =>
      (await unwrap(api.GET('/api/v1/contacts/', { params: { query: { search: search || undefined, page_size: 20 } }, signal }))).results,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}
