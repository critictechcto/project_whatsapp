import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { workspaceKeys } from '../../../api/queryKeys'
import type { Schemas } from '../../../api/types'
import { useWorkspace } from '../../../lib/workspace'

export type WhatsAppAccount = Schemas['WhatsAppBusinessAccount']

/** Query keys for this area: `['ws', workspaceId, 'whatsapp', ...]`. */
export const whatsappKeys = workspaceKeys('whatsapp')

export function isOnboardingInProgress(account: Pick<WhatsAppAccount, 'onboarding_status'>) {
  return account.onboarding_status !== 'completed' && account.onboarding_status !== 'failed'
}

/** Connected WhatsApp Business Accounts with their numbers. Polls while a setup is still running. */
export function useWhatsAppAccounts() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: whatsappKeys.custom(workspaceId, 'accounts'),
    queryFn: async ({ signal }) => {
      const page = await unwrap(api.GET('/api/v1/whatsapp/accounts/', { params: { query: { page_size: 50 } }, signal }))
      return page.results
    },
    refetchInterval: (query) => (query.state.data?.some(isOnboardingInProgress) ? 3000 : false),
  })
}

export function useSignupConfig(enabled: boolean) {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: whatsappKeys.custom(workspaceId, 'signup-config'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/whatsapp/signup-config/', { signal })),
    enabled,
    staleTime: 10 * 60_000,
  })
}
