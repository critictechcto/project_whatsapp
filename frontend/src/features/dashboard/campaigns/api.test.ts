import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { campaignKeys, storeCampaign, type Campaign } from './api'

const campaign = (id: string, name: string) => ({ id, name, status: 'running' }) as unknown as Campaign
const page = (results: Campaign[]) => ({ results, next: null, previous: null })

describe('storeCampaign', () => {
  it('patches infinite lists and the single pages home caches under the same prefix', () => {
    const queryClient = new QueryClient()
    const ws = 'ws-1'
    queryClient.setQueryData(campaignKeys.list(ws, { status: 'running' }), { pages: [page([campaign('a', 'Old')])], pageParams: [undefined] })
    queryClient.setQueryData(campaignKeys.list(ws, { area: 'home', page_size: 50 }), page([campaign('a', 'Old'), campaign('b', 'Other')]))

    expect(() => storeCampaign(queryClient, ws, campaign('a', 'New'))).not.toThrow()

    const infinite = queryClient.getQueryData<{ pages: { results: Campaign[] }[] }>(campaignKeys.list(ws, { status: 'running' }))
    const single = queryClient.getQueryData<{ results: Campaign[] }>(campaignKeys.list(ws, { area: 'home', page_size: 50 }))
    expect(infinite?.pages[0].results[0].name).toBe('New')
    expect(single?.results.map((row) => row.name)).toEqual(['New', 'Other'])
  })
})
