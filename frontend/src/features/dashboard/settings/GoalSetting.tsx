import { Field, Select, Skeleton, useToast } from '../../../components/app'
import { useOnboarding, useUpdateOnboarding, type WorkspaceGoal } from '../onboarding/api'
import { goalLabel, goalOptions } from '../onboarding/goalSteps'
import { SectionCard } from './ui/SectionCard'

const options = goalOptions.map((option) => ({ value: option.value, label: option.title }))

/** Settings → General: the workspace's main goal, which orders the Home checklist for everyone. */
export function GoalSetting() {
  const onboarding = useOnboarding()
  const update = useUpdateOnboarding()
  const { toast } = useToast()
  const data = onboarding.data
  if (onboarding.isError) return null

  const onChange = (value: string) => {
    update.mutate(
      { goal: value as WorkspaceGoal | '' },
      {
        onSuccess: () => toast({ title: 'Main goal saved', tone: 'success' }),
        onError: () => toast({ title: "Couldn't save the main goal", tone: 'error' }),
      },
    )
  }

  return (
    <SectionCard id="settings-general" title="General" description="The main goal orders the setup steps on Home for everyone in this workspace.">
      {!data ? (
        <Skeleton className="h-10 w-full" />
      ) : data.can_set_goal ? (
        <Field label="Main goal">
          <Select
            value={data.goal ?? ''}
            onChange={(event) => onChange(event.target.value)}
            disabled={update.isPending}
            placeholder="Not chosen yet"
            options={options}
          />
        </Field>
      ) : (
        <dl className="text-sm">
          <dt className="text-[12.5px] text-muted">Main goal</dt>
          <dd className="mt-0.5 text-ink">{goalLabel(data.goal)}</dd>
          <dd className="mt-1 text-[12.5px] text-muted">An admin or the owner can change it.</dd>
        </dl>
      )}
    </SectionCard>
  )
}
