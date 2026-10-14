import { Checkbox, Skeleton, useToast } from '../../../components/app'
import { useOnboarding, useUpdateOnboarding, type WorkspaceGoal } from '../onboarding/api'
import { goalLabel, goalOptions, normalizeGoals } from '../onboarding/goalSteps'
import { SectionCard } from './ui/SectionCard'

/** Settings → General: the workspace's goals, which order the Home checklist for everyone. */
export function GoalSetting() {
  const onboarding = useOnboarding()
  const update = useUpdateOnboarding()
  const { toast } = useToast()
  const data = onboarding.data
  if (onboarding.isError) return null

  const toggle = (value: WorkspaceGoal, checked: boolean) => {
    const current = data?.goals ?? []
    const goals = normalizeGoals(checked ? [...current, value] : current.filter((goal) => goal !== value))
    update.mutate(
      { goals },
      {
        onSuccess: () => toast({ title: 'Goals saved', tone: 'success' }),
        onError: () => toast({ title: "Couldn't save the goals", tone: 'error' }),
      },
    )
  }

  return (
    <SectionCard id="settings-general" title="General" description="Your goals order the setup steps on Home for everyone in this workspace.">
      {!data ? (
        <Skeleton className="h-10 w-full" />
      ) : data.can_set_goal ? (
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-1 text-sm font-medium text-ink">Goals</legend>
          {goalOptions.map((option) => (
            <Checkbox
              key={option.value}
              label={option.title}
              description={option.description}
              checked={data.goals?.includes(option.value) ?? false}
              disabled={update.isPending}
              onChange={(event) => toggle(option.value, event.target.checked)}
            />
          ))}
        </fieldset>
      ) : (
        <dl className="text-sm">
          <dt className="text-[12.5px] text-muted">Goals</dt>
          <dd className="mt-0.5 text-ink">{goalLabel(data.goals)}</dd>
          <dd className="mt-1 text-[12.5px] text-muted">An admin or the owner can change it.</dd>
        </dl>
      )}
    </SectionCard>
  )
}
