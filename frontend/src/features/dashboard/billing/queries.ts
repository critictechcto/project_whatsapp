import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { useCursorQuery } from '../../../api/pagination'
import { workspaceKeys } from '../../../api/queryKeys'
import type { Schemas } from '../../../api/types'
import { useWorkspace } from '../../../lib/workspace'

/** Query keys for this area: `['ws', workspaceId, 'billing', ...]`. */
export const billingKeys = workspaceKeys('billing')

export const subscriptionKey = (workspaceId: string) => billingKeys.custom(workspaceId, 'subscription')
export const profileKey = (workspaceId: string) => billingKeys.custom(workspaceId, 'profile')

/** Polls every 3 seconds while a payment is being confirmed (`pending`). */
export function useSubscription() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: subscriptionKey(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/billing/subscription/', { signal })),
    refetchInterval: (query) => (query.state.data?.status === 'pending' ? 3000 : false),
  })
}

export function usePlans() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: billingKeys.custom(workspaceId, 'plans'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/billing/plans/', { signal })),
    staleTime: 10 * 60_000,
  })
}

export function useUsage() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: billingKeys.custom(workspaceId, 'usage'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/billing/usage/', { signal })),
  })
}

export function useBillingProfile() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: profileKey(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/billing/billing-profile/', { signal })),
  })
}

export function useInvoices() {
  const { workspaceId } = useWorkspace()
  return useCursorQuery<Schemas['Invoice']>({
    queryKey: billingKeys.list(workspaceId, { kind: 'invoices' }),
    queryFn: ({ cursor, signal }) => unwrap(api.GET('/api/v1/billing/invoices/', { params: { query: { cursor } }, signal })),
  })
}

export function isProfileComplete(profile: Schemas['BillingProfile'] | undefined): boolean {
  return Boolean(
    profile && profile.legal_name && profile.email && profile.address_line1 && profile.city && profile.state_code && profile.postal_code,
  )
}
