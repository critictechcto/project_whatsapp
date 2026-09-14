import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Pencil, Plus, Tags, Trash2, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'
import { api, unwrap } from '../../../../api/client'
import { applyApiErrorToForm, errorMessage, isApiError } from '../../../../api/errors'
import { Button, Dialog, EmptyState, Field, Input, PageHeader, Table, useToast, type Column } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { formatDate } from '../../../../lib/datetime'
import { useWorkspace } from '../../../../lib/workspace'
import { contactKeys, useInvalidateContacts, useTags } from '../api'
import { ConfirmDialog, FormError, TagChip } from '../components/shared'
import type { Tag } from '../lib/types'

const SWATCHES = ['#1d7f55', '#1f5a8c', '#8a5d0c', '#a3461f', '#6b4c9a', '#b03a6f', '#2f7f7a', '#5c6a63'] as const
const USAGE_PAGE = 200

export function TagsPage() {
  const { workspaceId, timeZone, can } = useWorkspace()
  const canWrite = can('agent')
  const { tags, isLoading, isError, refetch } = useTags()
  const [editing, setEditing] = useState<Tag | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Tag | null>(null)

  const columns: Column<Tag>[] = [
    { id: 'name', header: 'Tag', cell: (tag) => <TagChip tag={tag} /> },
    {
      id: 'color',
      header: 'Colour',
      hideOnMobile: true,
      cell: (tag) => <span className="font-mono text-[13px] text-ink-2">{tag.color || '—'}</span>,
    },
    { id: 'created', header: 'Created', hideOnMobile: true, cell: (tag) => formatDate(tag.created_at, timeZone) },
    ...(canWrite
      ? [
          {
            id: 'actions',
            header: <span className="sr-only">Actions</span>,
            align: 'right' as const,
            cell: (tag: Tag) => (
              <div className="flex justify-end gap-1">
                <Button variant="ghost" size="icon-sm" aria-label={`Edit ${tag.name}`} onClick={() => setEditing(tag)}>
                  <Pencil className="size-4" aria-hidden="true" />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label={`Delete ${tag.name}`} onClick={() => setDeleting(tag)}>
                  <Trash2 className="size-4" aria-hidden="true" />
                </Button>
              </div>
            ),
          },
        ]
      : []),
  ]

  return (
    <div className="flex flex-col gap-6">
      <Link to={`/app/w/${workspaceId}/contacts`} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden="true" />
        Contacts
      </Link>
      <PageHeader
        title="Tags"
        description="Group contacts for campaign audiences and filters. Tags are shared by everyone in the workspace."
        actions={
          canWrite && (
            <Button icon={<Plus className="size-4" aria-hidden="true" />} onClick={() => setEditing('new')}>
              New tag
            </Button>
          )
        }
      />
      {isError ? (
        <EmptyState
          icon={<TriangleAlert />}
          title="Tags didn't load"
          action={
            <Button variant="secondary" onClick={() => void refetch()}>
              Try again
            </Button>
          }
        />
      ) : (
        <Table
          caption="Tags"
          columns={columns}
          rows={tags}
          getRowId={(tag) => tag.id}
          loading={isLoading}
          empty={
            <EmptyState
              icon={<Tags />}
              title="No tags yet"
              description="Create tags like VIP, Wholesale or Diwali 2026 to group your contacts."
              action={canWrite ? <Button onClick={() => setEditing('new')}>New tag</Button> : undefined}
            />
          }
        />
      )}

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)} title={editing === 'new' ? 'New tag' : 'Edit tag'}>
        {editing !== null && <TagForm tag={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
      </Dialog>
      {deleting && <DeleteTagDialog tag={deleting} workspaceId={workspaceId} onClose={() => setDeleting(null)} />}
    </div>
  )
}

const schema = z.object({
  name: z.string().trim().min(1, 'Enter a name.').max(64, 'Use at most 64 characters.'),
  color: z
    .string()
    .trim()
    .refine((value) => !value || /^#[0-9a-fA-F]{6}$/.test(value), 'Use a hex colour such as #25D366.'),
})

type TagValues = z.infer<typeof schema>

function TagForm({ tag, onClose }: { tag?: Tag; onClose: () => void }) {
  const invalidate = useInvalidateContacts()
  const { toast } = useToast()
  const {
    control,
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<TagValues>({ resolver: zodResolver(schema), defaultValues: { name: tag?.name ?? '', color: tag?.color ?? '' } })
  const color = useWatch({ control, name: 'color' })
  const name = useWatch({ control, name: 'name' })

  const onSubmit = handleSubmit(async (values) => {
    try {
      if (tag) await unwrap(api.PATCH('/api/v1/contacts/tags/{id}/', { params: { path: { id: tag.id } }, body: values }))
      else await unwrap(api.POST('/api/v1/contacts/tags/', { body: values }))
      void invalidate()
      toast({ title: tag ? 'Tag saved' : 'Tag created', tone: 'success' })
      onClose()
    } catch (error) {
      if (isApiError(error, 'conflict')) {
        setError('name', { type: 'server', message: error.message }, { shouldFocus: true })
        return
      }
      applyApiErrorToForm(error, setError, { fields: ['name', 'color'] })
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <FormError message={errors.root?.server?.message} />
      <Field label="Name" required error={errors.name?.message}>
        <Input maxLength={64} {...register('name')} />
      </Field>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-[13px] font-medium text-ink">Colour</legend>
        <div className="flex flex-wrap gap-2">
          {[...SWATCHES, ''].map((swatch) => (
            <label
              key={swatch || 'none'}
              className={cn(
                'relative grid size-8 cursor-pointer place-items-center rounded-full border-2 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/40',
                color.toLowerCase() === swatch.toLowerCase() ? 'border-ink' : 'border-transparent',
              )}
            >
              <input
                type="radio"
                name="tag-colour"
                className="sr-only"
                checked={color.toLowerCase() === swatch.toLowerCase()}
                onChange={() => setValue('color', swatch, { shouldValidate: true })}
              />
              <span
                aria-hidden="true"
                className={cn('size-6 rounded-full', !swatch && 'border border-dashed border-line bg-card')}
                style={swatch ? { backgroundColor: swatch } : undefined}
              />
              <span className="sr-only">{swatch || 'No colour'}</span>
            </label>
          ))}
        </div>
        <Field label="Hex colour" hideLabel error={errors.color?.message} className="max-w-40">
          <Input placeholder="#25D366" className="font-mono" {...register('color')} />
        </Field>
      </fieldset>
      <div className="flex items-center gap-2 text-[13px] text-muted">
        Preview <TagChip tag={{ name: name.trim() || 'Tag name', color: /^#[0-9a-fA-F]{6}$/.test(color) ? color : '' }} />
      </div>
      <div className="-mx-5 -mb-4 mt-1 flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">
        <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="submit" loading={isSubmitting}>
          {tag ? 'Save tag' : 'Create tag'}
        </Button>
      </div>
    </form>
  )
}

function DeleteTagDialog({ tag, workspaceId, onClose }: { tag: Tag; workspaceId: string; onClose: () => void }) {
  const invalidate = useInvalidateContacts()
  const { toast } = useToast()
  const [pending, setPending] = useState(false)

  // The API has no counts, so load up to one page of tagged contacts.
  const usage = useQuery({
    queryKey: contactKeys.list(workspaceId, { tag: tag.id, usage: true }),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/contacts/', { params: { query: { tag: tag.id, page_size: USAGE_PAGE } }, signal })),
  })
  const usageText = usage.isLoading
    ? 'Checking how many contacts use it…'
    : usage.data
      ? usage.data.next
        ? `It's on more than ${USAGE_PAGE} contacts.`
        : usage.data.results.length === 0
          ? 'No contacts have this tag.'
          : `It's on ${usage.data.results.length} ${usage.data.results.length === 1 ? 'contact' : 'contacts'}.`
      : null

  const confirm = async () => {
    setPending(true)
    try {
      await unwrap(api.DELETE('/api/v1/contacts/tags/{id}/', { params: { path: { id: tag.id } } }))
      void invalidate()
      toast({ title: `Deleted "${tag.name}"`, tone: 'success' })
      onClose()
    } catch (error) {
      setPending(false)
      toast({ title: "Couldn't delete the tag", description: errorMessage(error), tone: 'error' })
    }
  }

  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      danger
      loading={pending}
      title={`Delete "${tag.name}"?`}
      confirmLabel="Delete tag"
      onConfirm={() => void confirm()}
    >
      <div className="flex flex-col gap-2 text-sm text-ink-2">
        {usageText && <p aria-live="polite">{usageText}</p>}
        <p className="text-muted">
          The tag is removed from those contacts; the contacts themselves stay. Campaign audiences that use this tag won't match it any
          more.
        </p>
      </div>
    </ConfirmDialog>
  )
}
