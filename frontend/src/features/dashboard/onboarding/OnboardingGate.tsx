import { lazy, Suspense } from 'react'
import { useWorkspace } from '../../../lib/workspace'
import { useOnboarding } from './api'

const WelcomeFlow = lazy(() => import('./WelcomeFlow'))

/**
 * Mounted once in the shell: shows the welcome flow to people who haven't seen it in this workspace
 * (docs/contracts/onboarding.md). Nothing while loading or when the state can't be read.
 */
export function OnboardingGate() {
  const { workspaceId } = useWorkspace()
  const onboarding = useOnboarding()
  if (onboarding.data?.welcome_completed !== false) return null
  return (
    <Suspense fallback={null}>
      <WelcomeFlow key={workspaceId} onboarding={onboarding.data} />
    </Suspense>
  )
}
