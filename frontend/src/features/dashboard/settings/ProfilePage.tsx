import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, LogOut } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm } from '../../../api/errors'
import { queryKeys } from '../../../api/queryKeys'
import type { Me } from '../../../api/types'
import { Button, Field, Input, PageHeader, PageSpinner, useToast } from '../../../components/app'
import { formatDate } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { PasswordInput } from '../auth/PasswordInput'
import { useLogout, useMe } from '../auth/session'
import { RoleBadge } from '../team/RoleBadge'
import { SectionCard } from './ui/SectionCard'

const nameSchema = z.object({
  full_name: z.string().trim().min(1, 'Enter your name.').max(150, 'Use 150 characters or fewer.'),
})
type NameValues = z.infer<typeof nameSchema>

const passwordSchema = z
  .object({
    current_password: z.string().min(1, 'Enter your current password.'),
    new_password: z.string().min(8, 'Use at least 8 characters.'),
    confirm_password: z.string().min(1, 'Type the new password again.'),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    path: ['confirm_password'],
    message: "The passwords don't match.",
  })
  .refine((values) => values.new_password !== values.current_password, {
    path: ['new_password'],
    message: 'Choose a password different from your current one.',
  })
type PasswordValues = z.infer<typeof passwordSchema>

export function ProfilePage() {
  const me = useMe()
  const { workspaceId } = useWorkspace()

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={`/app/w/${workspaceId}/settings`} className="inline-flex items-center gap-1 hover:text-ink">
            <ArrowLeft className="size-3" aria-hidden="true" /> Settings
          </Link>
        }
        title="Your profile"
        description="These details apply to your account in every workspace."
      />
      {me.data ? (
        <>
          <NameSection me={me.data} />
          <PasswordSection />
          <WorkspacesSection me={me.data} />
          <SessionSection />
        </>
      ) : (
        <PageSpinner label="Loading your profile" />
      )}
    </div>
  )
}

function NameSection({ me }: { me: Me }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<NameValues>({ resolver: zodResolver(nameSchema), defaultValues: { full_name: me.full_name ?? '' } })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const updated = await unwrap(api.PATCH('/api/v1/auth/me/', { body: values }))
      queryClient.setQueryData(queryKeys.me, updated)
      reset({ full_name: updated.full_name ?? '' })
      toast({ title: 'Profile saved', tone: 'success' })
    } catch (error) {
      applyApiErrorToForm(error, setError, { fields: ['full_name'] })
    }
  })

  return (
    <SectionCard
      id="profile-details"
      title="Details"
      footer={
        <Button type="submit" form="profile-details-form" loading={isSubmitting} disabled={!isDirty}>
          Save
        </Button>
      }
    >
      <form id="profile-details-form" onSubmit={onSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <FormError message={errors.root?.server?.message} />
        </div>
        <Field label="Full name" error={errors.full_name?.message} required>
          <Input autoComplete="name" {...register('full_name')} />
        </Field>
        <Field label="Email" hint={`Member since ${formatDate(me.date_joined)}.`}>
          <Input value={me.email} readOnly disabled />
        </Field>
      </form>
    </SectionCard>
  )
}

function PasswordSection() {
  const { toast } = useToast()
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: '', new_password: '', confirm_password: '' },
  })

  const onSubmit = handleSubmit(async ({ current_password, new_password }) => {
    try {
      await unwrap(api.POST('/api/v1/auth/password/change/', { body: { current_password, new_password } }))
      reset()
      toast({ title: 'Password changed', description: 'Use the new password the next time you log in.', tone: 'success' })
    } catch (error) {
      applyApiErrorToForm(error, setError, { fields: ['current_password', 'new_password'] })
    }
  })

  return (
    <SectionCard
      id="profile-password"
      title="Password"
      description="Use at least 8 characters. Avoid a password you use on other sites."
      footer={
        <Button type="submit" form="profile-password-form" loading={isSubmitting}>
          Change password
        </Button>
      }
    >
      <form id="profile-password-form" onSubmit={onSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-4 sm:col-span-2">
          <FormError message={errors.root?.server?.message} />
          <Field label="Current password" error={errors.current_password?.message} required className="sm:max-w-[calc(50%-0.5rem)]">
            <PasswordInput autoComplete="current-password" {...register('current_password')} />
          </Field>
        </div>
        <Field label="New password" error={errors.new_password?.message} required>
          <PasswordInput autoComplete="new-password" {...register('new_password')} />
        </Field>
        <Field label="Confirm new password" error={errors.confirm_password?.message} required>
          <PasswordInput autoComplete="new-password" {...register('confirm_password')} />
        </Field>
      </form>
    </SectionCard>
  )
}

function WorkspacesSection({ me }: { me: Me }) {
  const { workspaceId } = useWorkspace()
  return (
    <SectionCard id="profile-workspaces" title="Your workspaces" description="Workspaces you belong to and your role in each.">
      <ul className="-my-2 divide-y divide-line-2">
        {me.memberships.map((membership) => (
          <li key={membership.workspace_id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
            <Link to={`/app/w/${membership.workspace_id}`} className="min-w-0 truncate text-sm font-medium text-ink hover:underline">
              {membership.workspace_name}
              {membership.workspace_id === workspaceId && <span className="ml-2 text-[12.5px] font-normal text-muted">Current</span>}
            </Link>
            <RoleBadge role={membership.role} />
          </li>
        ))}
      </ul>
    </SectionCard>
  )
}

function SessionSection() {
  const logout = useLogout()
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)

  return (
    <SectionCard
      id="profile-session"
      title="Session"
      description="Log out of UpChatz on this device."
      actions={
        <Button
          variant="secondary"
          loading={pending}
          icon={<LogOut className="size-4" aria-hidden="true" />}
          onClick={() => {
            setPending(true)
            void logout().then(() => navigate('/app/login?reason=signed_out', { replace: true }))
          }}
        >
          Log out
        </Button>
      }
    />
  )
}
