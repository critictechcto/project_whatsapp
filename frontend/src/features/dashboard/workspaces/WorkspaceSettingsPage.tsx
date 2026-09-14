import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm } from '../../../api/errors'
import { queryKeys } from '../../../api/queryKeys'
import { Button, Field, Input, PageHeader, useToast } from '../../../components/app'
import { DEFAULT_TIME_ZONE, formatDate } from '../../../lib/datetime'
import { roleLabels } from '../../../lib/roles'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { ConfirmDialog } from '../settings/ui/ConfirmDialog'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { exitWorkspace } from './exitWorkspace'
import { workspaceSchema, type WorkspaceValues } from './schema'
import { TimeZoneCombobox } from './TimeZoneCombobox'

/** `settings/workspace`: rename and time zone (admin+), delete (owner). */
export function WorkspaceSettingsPage() {
  const { workspace, workspaceId, role, can } = useWorkspace()
  const canEdit = can('admin')
  const isOwner = can('owner')
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const {
    control,
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<WorkspaceValues>({
    resolver: zodResolver(workspaceSchema),
    defaultValues: { name: workspace.name, time_zone: workspace.time_zone || DEFAULT_TIME_ZONE },
  })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const updated = await unwrap(api.PATCH('/api/v1/workspaces/{id}/', { params: { path: { id: workspaceId } }, body: values }))
      queryClient.setQueryData([...queryKeys.workspaces, workspaceId], updated)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.workspaces }),
        queryClient.invalidateQueries({ queryKey: queryKeys.me }),
      ])
      reset({ name: updated.name, time_zone: updated.time_zone || values.time_zone })
      toast({ title: 'Workspace settings saved', tone: 'success' })
    } catch (error) {
      applyApiErrorToForm(error, setError, { fields: ['name', 'time_zone'] })
    }
  })

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={`/app/w/${workspaceId}/settings`} className="inline-flex items-center gap-1 hover:text-ink">
            <ArrowLeft className="size-3" aria-hidden="true" /> Settings
          </Link>
        }
        title="Workspace settings"
        description="The name your team sees and the time zone used for schedules and dates."
      />

      {!canEdit && (
        <Notice title="View only">
          Your role is {roleLabels[role]}. Only admins and the owner can change workspace settings.
        </Notice>
      )}

      <SectionCard
        id="workspace-general"
        title="General"
        footer={
          canEdit && (
            <>
              <Button variant="ghost" disabled={!isDirty || isSubmitting} onClick={() => reset()}>
                Discard
              </Button>
              <Button type="submit" form="workspace-general-form" loading={isSubmitting} disabled={!isDirty}>
                Save changes
              </Button>
            </>
          )
        }
      >
        <form id="workspace-general-form" onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
          <FormError message={errors.root?.server?.message} />
          <Field label="Workspace name" error={errors.name?.message} required={canEdit}>
            <Input autoComplete="organization" disabled={!canEdit} {...register('name')} />
          </Field>
          <Field
            label="Time zone"
            hint="Campaign schedules, business hours and dates across the dashboard use this zone."
            error={errors.time_zone?.message}
            required={canEdit}
          >
            <Controller
              control={control}
              name="time_zone"
              render={({ field }) => (
                <TimeZoneCombobox value={field.value} onChange={field.onChange} onBlur={field.onBlur} disabled={!canEdit} />
              )}
            />
          </Field>
          <dl className="grid gap-x-6 gap-y-2 border-t border-line-2 pt-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-[12.5px] text-muted">URL name</dt>
              <dd className="font-mono text-[13px] text-ink">{workspace.slug}</dd>
            </div>
            <div>
              <dt className="text-[12.5px] text-muted">Created</dt>
              <dd className="text-ink">{formatDate(workspace.created_at, workspace.time_zone || DEFAULT_TIME_ZONE)}</dd>
            </div>
            <div>
              <dt className="text-[12.5px] text-muted">Your role</dt>
              <dd className="text-ink">{roleLabels[role]}</dd>
            </div>
          </dl>
        </form>
      </SectionCard>

      {isOwner && <DeleteWorkspaceSection />}
    </div>
  )
}

function DeleteWorkspaceSection() {
  const { workspace, workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { toast } = useToast()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')

  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE('/api/v1/workspaces/{id}/', { params: { path: { id: workspaceId } } })),
    onSuccess: () => {
      exitWorkspace(queryClient, navigate, workspaceId)
      toast({ title: `${workspace.name} was deleted`, tone: 'success' })
    },
  })

  const matches = typed.trim() === workspace.name

  return (
    <SectionCard
      id="workspace-danger"
      tone="danger"
      title="Delete workspace"
      description="Deletes the workspace for everyone, including its contacts, conversations, templates and team access. This can't be undone."
      actions={
        <Button
          variant="danger"
          icon={<Trash2 className="size-4" aria-hidden="true" />}
          onClick={() => {
            setTyped('')
            remove.reset()
            setOpen(true)
          }}
        >
          Delete workspace
        </Button>
      }
    >
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Delete ${workspace.name}?`}
        description="Your WhatsApp Business Account stays with Meta, but it will no longer be connected here."
        confirmLabel="Delete workspace"
        loading={remove.isPending}
        confirmDisabled={!matches}
        onConfirm={() => remove.mutate()}
      >
        <div className="flex flex-col gap-3">
          <FormError message={remove.isError ? actionErrorMessage(remove.error) : undefined} />
          <Field label={<>Type <span className="font-mono">{workspace.name}</span> to confirm</>}>
            <Input value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" />
          </Field>
        </div>
      </ConfirmDialog>
    </SectionCard>
  )
}
