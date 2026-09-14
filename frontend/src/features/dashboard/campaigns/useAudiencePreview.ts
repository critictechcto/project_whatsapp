import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, unwrap } from '../../../api/client'
import type { Schemas } from '../../../api/types'
import { campaignKeys, storeCampaign } from './api'

type Audience = Schemas['CampaignAudienceRequest']

/** `value` once it has stopped changing for `delayMs`. Compares by JSON, so new objects with the same content don't reset it. */
export function useDebouncedJson<T>(value: T, delayMs: number): T {
  const json = JSON.stringify(value)
  const [debounced, setDebounced] = useState(json)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(json), delayMs)
    return () => clearTimeout(timer)
  }, [json, delayMs])
  return JSON.parse(debounced) as T
}

export function audienceIsEmpty(audience: Audience): boolean {
  return !audience.tag_ids?.length && !audience.contact_ids?.length
}

/**
 * Live audience counts. The preview endpoint counts the campaign's saved audience, so the
 * (still editable) campaign is patched with the audience first.
 */
export function useAudiencePreview(workspaceId: string, campaignId: string | undefined, audience: Audience, delayMs = 300) {
  const queryClient = useQueryClient()
  const debounced = useDebouncedJson(audience, delayMs)
  const empty = audienceIsEmpty(debounced)

  const query = useQuery({
    queryKey: campaignKeys.custom(workspaceId, 'audience-preview', campaignId ?? '', debounced),
    queryFn: async ({ signal }) => {
      const id = campaignId ?? ''
      const saved = await unwrap(api.PATCH('/api/v1/campaigns/{id}/', { params: { path: { id } }, body: { audience: debounced }, signal }))
      storeCampaign(queryClient, workspaceId, saved)
      return unwrap(api.POST('/api/v1/campaigns/{id}/audience-preview/', { params: { path: { id } }, signal }))
    },
    enabled: Boolean(campaignId) && !empty,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  })

  return { ...query, empty }
}
