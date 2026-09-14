import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { api, unwrap } from '../../../api/client'
import { ApiError, applyApiErrorToForm, isApiError } from '../../../api/errors'
import { Button, Dialog, Field, Input, Select, useToast } from '../../../components/app'
import { formatDate } from '../../../lib/datetime'
import { roleLabels } from '../../../lib/roles'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { actionErrorMessage } from '../settings/ui/hooks'
import { teamKeys } from './queries'
import { assignableRoles, roleDescriptions } from './roles'

const inviteSchema = z.object({
  email: z.email('Enter a valid email address.'),
  role: z.enum(['admin', 'agent', 'viewer']),
})
type InviteValues = z.infer<typeof inviteSchema>

type InviteDialogProps = { open: boolean; onOpenChange: (open: boolean) => void; onInvited?: () => void }

export function InviteDialog({ open, onOpenChange, onInvited }: InviteDialogProps) {
  const { workspace, workspaceId, timeZone } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const {
    control,
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<InviteValues>({ resolver: zodResolver(inviteSchema), defaultValues: { email: '', role: 'agent' } })
  const role = useWatch({ control, name: 'role' })

  const close = (next: boolean) => {
    if (isSubmitting) return
    if (!next) reset()
    onOpenChange(next)
  }

  const onSubmit = handleSubmit(async (values) => {
    try {
      const invitation = await unwrap(api.POST('/api/v1/workspaces/invitations/', { body: values }))
      await queryClient.invalidateQueries({ queryKey: teamKeys.all(workspaceId) })
      toast({
        title: `Invitation sent to ${invitation.email}`,
        description: `The link to join ${workspace.name} works until ${formatDate(invitation.expires_at, timeZone)}.`,
        tone: 'success',
      })
      reset()
      onOpenChange(false)
      onInvited?.()
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setError('root.server', { message: actionErrorMessage(error) })
      } else if (isApiError(error, 'conflict')) {
        setError('email', { message: error.message })
      } else {
        applyApiErrorToForm(error, setError, { fields: ['email', 'role'] })
      }
    }
  })

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      dismissible={!isSubmitting}
      title="Invite a teammate"
      description="They'll get an email with a link to join. Use the address they'll sign in with."
      footer={
        <>
          <Button variant="secondary" disabled={isSubmitting} onClick={() => close(false)}>
            Cancel
          </Button>
          <Button type="submit" form="invite-form" loading={isSubmitting}>
            Send invitation
          </Button>
        </>
      }
    >
      <form id="invite-form" onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <FormError message={errors.root?.server?.message} />
        <Field label="Email" error={errors.email?.message} required>
          <Input type="email" autoComplete="off" placeholder="name@business.in" {...register('email')} />
        </Field>
        <Field label="Role" hint={roleDescriptions[role]} error={errors.role?.message} required>
          <Select options={assignableRoles.map((value) => ({ value, label: roleLabels[value] }))} {...register('role')} />
        </Field>
      </form>
    </Dialog>
  )
}
