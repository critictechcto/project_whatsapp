import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { workspaceKeys } from '../../../api/queryKeys'
import type { Schemas } from '../../../api/types'
import { useWorkspace } from '../../../lib/workspace'

/** Onboarding state of the signed-in person in this workspace (docs/contracts/onboarding.md). */
export type Onboarding = Schemas['Onboarding']
export type OnboardingUpdate = Schemas['PatchedOnboardingRequest']
export type WorkspaceGoal = Schemas['WorkspaceGoalEnum']

export const onboardingKeys = workspaceKeys('onboarding')

export function useOnboarding() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: onboardingKeys.all(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/workspaces/onboarding/', { signal })),
    staleTime: Infinity,
  })
}

/** PATCHes the caller's flags (and the goal, for admins); the cache is updated optimistically. */
export function useUpdateOnboarding() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const key = onboardingKeys.all(workspaceId)
  return useMutation({
    mutationFn: (body: OnboardingUpdate) => unwrap(api.PATCH('/api/v1/workspaces/onboarding/', { body })),
    onMutate: async (body) => {
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<Onboarding>(key)
      if (previous) queryClient.setQueryData<Onboarding>(key, { ...previous, ...body })
      return { previous }
    },
    onError: (_error, _body, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous)
    },
    onSuccess: (data) => queryClient.setQueryData(key, data),
  })
}
