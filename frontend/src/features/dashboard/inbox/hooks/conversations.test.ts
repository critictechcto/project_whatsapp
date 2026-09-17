import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { inboxKeys, type Conversation } from '../api'
import { findListedConversation, patchConversation } from './conversations'

const conversation = (id: string) => ({ id, status: 'open' }) as unknown as Conversation
const page = (results: Conversation[]) => ({ results, next: null, previous: null })

describe('conversation cache helpers', () => {
  it('skip the single pages home caches under the inbox list prefix', () => {
    const queryClient = new QueryClient()
    const ws = 'ws-1'
    queryClient.setQueryData(inboxKeys.list(ws, { area: 'home', status: 'open' }), page([conversation('c1')]))
    queryClient.setQueryData(inboxKeys.list(ws, { status: 'open' }), { pages: [page([conversation('c1')])], pageParams: [undefined] })

    expect(() =>
      patchConversation(queryClient, ws, 'c1', (current) => ({ ...current, status: 'closed' }) as Conversation),
    ).not.toThrow()
    expect(findListedConversation(queryClient, ws, 'c1')?.status).toBe('closed')
  })
})
