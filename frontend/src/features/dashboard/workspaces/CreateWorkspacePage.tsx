import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router'
import { z } from 'zod'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm } from '../../../api/errors'
import { queryKeys } from '../../../api/queryKeys'
import { Button, Field, Input, Select } from '../../../components/app'
import { commonTimeZones, DEFAULT_TIME_ZONE } from '../../../lib/datetime'
import { AuthLayout, AuthLink } from '../auth/AuthLayout'
import { FormError } from '../auth/FormError'
import { useLogout, useMe } from '../auth/session'

const schema = z.object({
  name: z.string().trim().min(2, 'Use at least 2 characters.').max(120),
  time_zone: z.string().min(1),
})

type WorkspaceValues = z.infer<typeof schema>

export function CreateWorkspacePage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const me = useMe()
  const logout = useLogout()
  const hasWorkspaces = (me.data?.memberships.length ?? 0) > 0

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<WorkspaceValues>({ resolver: zodResolver(schema), defaultValues: { name: '', time_zone: DEFAULT_TIME_ZONE } })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const workspace = await unwrap(api.POST('/api/v1/workspaces/', { body: values }))
      await Promise.all([
        queryClient.refetchQueries({ queryKey: queryKeys.me }),
        queryClient.invalidateQueries({ queryKey: queryKeys.workspaces }),
      ])
      navigate(`/app/w/${workspace.id}`, { replace: true })
    } catch (error) {
      applyApiErrorToForm(error, setError, { fields: ['name', 'time_zone'] })
    }
  })

  return (
    <AuthLayout
      title={hasWorkspaces ? 'Create a workspace' : 'Set up your workspace'}
      description="A workspace holds one business: its WhatsApp numbers, contacts, templates and team."
      footer={
        hasWorkspaces ? (
          <AuthLink to="/app">Back to your workspace</AuthLink>
        ) : (
          <button
            type="button"
            className="font-medium text-accent-2 underline-offset-2 hover:underline"
            onClick={() => void logout().then(() => navigate('/app/login', { replace: true }))}
          >
            Log out
          </button>
        )
      }
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <FormError message={errors.root?.server?.message} />
        <Field label="Business name" hint="Shown to your team, not to customers." error={errors.name?.message} required>
          <Input autoComplete="organization" placeholder="e.g. Sharma Sweets" {...register('name')} />
        </Field>
        <Field label="Time zone" hint="Used for scheduling campaigns and reports." error={errors.time_zone?.message} required>
          <Select options={commonTimeZones.map((zone) => ({ value: zone, label: zone.replace('_', ' ') }))} {...register('time_zone')} />
        </Field>
        <Button type="submit" loading={isSubmitting} className="mt-1 w-full">
          Create workspace
        </Button>
      </form>
    </AuthLayout>
  )
}
