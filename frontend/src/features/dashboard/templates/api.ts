import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { useCursorQuery } from '../../../api/pagination'
import type { MessageTemplate, Schemas, TemplateCategory, TemplateStatus } from '../../../api/types'
import { templateKeys } from '../../../components/app/whatsapp/templateKeys'
import { useWorkspace } from '../../../lib/workspace'

export { templateKeys }

export type TemplateFilters = {
  status?: TemplateStatus
  category?: TemplateCategory
  language?: string
  search?: string
}

export function useTemplateList(filters: TemplateFilters) {
  const { workspaceId } = useWorkspace()
  const query = { ...filters, search: filters.search || undefined, page_size: 50 }
  return useCursorQuery<MessageTemplate>({
    queryKey: templateKeys.list(workspaceId, { area: 'templates', ...query }),
    queryFn: ({ cursor, signal }) => unwrap(api.GET('/api/v1/templates/', { params: { query: { ...query, cursor } }, signal })),
  })
}

export function useTemplate(id: string | undefined, { pollWhilePending = false }: { pollWhilePending?: boolean } = {}) {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: templateKeys.detail(workspaceId, id ?? ''),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/templates/{id}/', { params: { path: { id: id ?? '' } }, signal })),
    enabled: Boolean(id),
    // Meta reviews asynchronously; keep a pending template fresh while it is on screen.
    refetchInterval: (query) => (pollWhilePending && query.state.data?.status === 'PENDING' ? 5_000 : false),
  })
}

/** WhatsApp Business Accounts a template can belong to. */
export function useWhatsAppAccounts() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: templateKeys.custom(workspaceId, 'whatsapp-accounts'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/whatsapp/accounts/', { params: { query: { page_size: 50 } }, signal })),
  })
}

export type SaveResult = {
  template: MessageTemplate
  /** Set when the template was saved but submitting it to Meta failed. */
  submitError: unknown
}

/**
 * Saves the template (create, or PATCH when editing) and submits it to Meta for review.
 * Validation errors from saving throw; a failed submission resolves with the saved draft and `submitError`.
 */
export function useSaveAndSubmitTemplate(editingId?: string) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: Schemas['MessageTemplateRequest']): Promise<SaveResult> => {
      const saved = editingId
        ? await unwrap(api.PATCH('/api/v1/templates/{id}/', { params: { path: { id: editingId } }, body }))
        : await unwrap(api.POST('/api/v1/templates/', { body }))
      try {
        const submitted = await unwrap(api.POST('/api/v1/templates/{id}/submit/', { params: { path: { id: saved.id } } }))
        return { template: submitted, submitError: null }
      } catch (submitError) {
        return { template: saved, submitError }
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: templateKeys.all(workspaceId) }),
    onSuccess: ({ template }) => queryClient.setQueryData(templateKeys.detail(workspaceId, template.id), template),
  })
}

export function useSubmitTemplate(id: string) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/templates/{id}/submit/', { params: { path: { id } } })),
    onSuccess: (template) => queryClient.setQueryData(templateKeys.detail(workspaceId, id), template),
    onSettled: () => queryClient.invalidateQueries({ queryKey: templateKeys.lists(workspaceId) }),
  })
}

export function useDeleteTemplate() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE('/api/v1/templates/{id}/', { params: { path: { id } } })),
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: templateKeys.detail(workspaceId, id) })
      return queryClient.invalidateQueries({ queryKey: templateKeys.all(workspaceId) })
    },
  })
}

export function useSyncTemplates() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/templates/sync/', { body: {} })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: templateKeys.all(workspaceId) }),
  })
}
