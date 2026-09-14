import { useQuery, useQueryClient, type InfiniteData, type QueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { workspaceKeys } from '../../../api/queryKeys'
import type { CursorPage, Schemas } from '../../../api/types'
import { useRealtimeEvent } from '../../../lib/realtime/hooks'

export type Campaign = Schemas['Campaign']
export type CampaignStatus = Schemas['CampaignStatusEnum']
export type CampaignStats = Schemas['CampaignStats']
export type CampaignWrite = Schemas['CampaignWriteRequest']
export type CampaignRecipient = Schemas['CampaignRecipient']
export type RecipientStatus = Schemas['RecipientStatusEnum']
export type AudiencePreview = Schemas['AudiencePreview']
export type VariableSource = Schemas['VariableSourceRequest']
export type VariableSourceType = Schemas['VariableSourceTypeEnum']

export const campaignKeys = workspaceKeys('campaigns')

export const campaignStatuses: readonly CampaignStatus[] = ['draft', 'scheduled', 'running', 'paused', 'completed', 'cancelled', 'failed']

export const recipientStatuses: readonly RecipientStatus[] = ['pending', 'skipped', 'queued', 'sent', 'delivered', 'read', 'failed']

export function fetchCampaign(id: string, signal?: AbortSignal): Promise<Campaign> {
  return unwrap(api.GET('/api/v1/campaigns/{id}/', { params: { path: { id } }, signal }))
}

export function useCampaign(workspaceId: string, id: string | undefined) {
  return useQuery({
    queryKey: campaignKeys.detail(workspaceId, id ?? ''),
    queryFn: ({ signal }) => fetchCampaign(id ?? '', signal),
    enabled: Boolean(id),
  })
}

type CampaignPages = InfiniteData<CursorPage<Campaign>, string | undefined>

function patchLists(queryClient: QueryClient, workspaceId: string, patch: (campaign: Campaign) => Campaign) {
  queryClient.setQueriesData<CampaignPages>({ queryKey: campaignKeys.lists(workspaceId) }, (data) =>
    data ? { ...data, pages: data.pages.map((page) => ({ ...page, results: page.results.map(patch) })) } : data,
  )
}

/** Writes a campaign returned by a mutation into the detail cache and every loaded list. */
export function storeCampaign(queryClient: QueryClient, workspaceId: string, campaign: Campaign) {
  queryClient.setQueryData(campaignKeys.detail(workspaceId, campaign.id), campaign)
  patchLists(queryClient, workspaceId, (current) => (current.id === campaign.id ? campaign : current))
}

/**
 * Applies `campaign.progress` frames to the cache: stats and status update in place, recipients
 * refetch. A status change also refetches the detail for timestamps such as `completed_at`.
 */
export function useCampaignProgress(workspaceId: string) {
  const queryClient = useQueryClient()
  useRealtimeEvent('campaign.progress', ({ campaign_id, status, stats }) => {
    const detailKey = campaignKeys.detail(workspaceId, campaign_id)
    const previous = queryClient.getQueryData<Campaign>(detailKey)
    const patch = (campaign: Campaign): Campaign => (campaign.id === campaign_id ? { ...campaign, status, stats } : campaign)

    if (previous) queryClient.setQueryData<Campaign>(detailKey, patch(previous))
    patchLists(queryClient, workspaceId, patch)
    void queryClient.invalidateQueries({ queryKey: campaignKeys.custom(workspaceId, 'recipients', campaign_id) })
    if (previous && previous.status !== status) void queryClient.invalidateQueries({ queryKey: detailKey })
  })
}
