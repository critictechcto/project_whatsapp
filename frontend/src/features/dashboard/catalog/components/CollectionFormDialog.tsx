import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { api, unwrap } from '../../../../api/client'
import { applyApiErrorToForm } from '../../../../api/errors'
import { Button, Checkbox, Dialog, Field, Input, Textarea, useToast } from '../../../../components/app'
import { useInvalidateCatalog } from '../api'
import type { Collection } from '../lib/types'
import { CharCount, FormError } from './shared'

export const COLLECTION_NAME_MAX = 24
export const COLLECTION_DESCRIPTION_MAX = 72

const schema = z.object({
  name: z.string().trim().min(1, 'Enter a collection name.').max(COLLECTION_NAME_MAX, `Use at most ${COLLECTION_NAME_MAX} characters: WhatsApp cuts list row titles there.`),
  description: z.string().trim().max(COLLECTION_DESCRIPTION_MAX, `Use at most ${COLLECTION_DESCRIPTION_MAX} characters: WhatsApp cuts list row descriptions there.`),
  isActive: z.boolean(),
})

type Values = z.infer<typeof schema>

type Props = { open: boolean; onOpenChange: (open: boolean) => void; collection?: Collection }

export function CollectionFormDialog({ open, onOpenChange, collection }: Props) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={collection ? 'Edit collection' : 'New collection'}
      description="Collections are the rows buyers pick from in your WhatsApp store menu."
    >
      {open && <CollectionForm collection={collection} onClose={() => onOpenChange(false)} />}
    </Dialog>
  )
}

function CollectionForm({ collection, onClose }: { collection?: Collection; onClose: () => void }) {
  const invalidate = useInvalidateCatalog()
  const { toast } = useToast()
  const {
    control,
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: collection?.name ?? '', description: collection?.description ?? '', isActive: collection?.is_active ?? true },
  })
  const name = useWatch({ control, name: 'name' })
  const description = useWatch({ control, name: 'description' })

  const onSubmit = handleSubmit(async (values) => {
    const body = { name: values.name, description: values.description, is_active: values.isActive }
    try {
      if (collection) await unwrap(api.PATCH('/api/v1/catalog/collections/{id}/', { params: { path: { id: collection.id } }, body }))
      else await unwrap(api.POST('/api/v1/catalog/collections/', { body }))
      void invalidate()
      toast({ title: collection ? 'Collection saved' : 'Collection created', tone: 'success' })
      onClose()
    } catch (error) {
      applyApiErrorToForm(error, setError, { fieldMap: { is_active: 'isActive' }, fields: ['name', 'description', 'isActive'] })
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <FormError message={errors.root?.server?.message} />
      <Field
        label="Name"
        required
        error={errors.name?.message}
        hint={
          <span className="flex justify-between gap-3">
            <span>Shown as a WhatsApp list row title.</span>
            <CharCount value={name} max={COLLECTION_NAME_MAX} />
          </span>
        }
      >
        <Input placeholder="Dry fruit sweets" {...register('name')} />
      </Field>
      <Field
        label="Description"
        error={errors.description?.message}
        hint={
          <span className="flex justify-between gap-3">
            <span>Optional. Shown under the title in the list.</span>
            <CharCount value={description} max={COLLECTION_DESCRIPTION_MAX} />
          </span>
        }
      >
        <Textarea rows={2} placeholder="Kaju katli, badam barfi and pista rolls" {...register('description')} />
      </Field>
      <Checkbox label="Active" description="Inactive collections are hidden from buyers." {...register('isActive')} />
      <div className="-mx-5 -mb-4 mt-1 flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">
        <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="submit" loading={isSubmitting}>
          {collection ? 'Save collection' : 'Create collection'}
        </Button>
      </div>
    </form>
  )
}
