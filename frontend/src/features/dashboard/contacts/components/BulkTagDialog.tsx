import { useState } from 'react'
import { api, unwrap } from '../../../../api/client'
import { errorMessage } from '../../../../api/errors'
import { Button, Dialog, Field, useToast } from '../../../../components/app'
import { formatNumber } from '../../../../lib/format'
import { useInvalidateContacts, useTags } from '../api'
import { FormError, TagPicker } from './shared'

type BulkTagDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'add' | 'remove'
  contactIds: readonly string[]
  onDone: () => void
}

export function BulkTagDialog({ open, onOpenChange, mode, contactIds, onDone }: BulkTagDialogProps) {
  const count = contactIds.length
  const noun = count === 1 ? 'contact' : 'contacts'
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={mode === 'add' ? 'Add tags' : 'Remove tags'}
      description={`${mode === 'add' ? 'Add tags to' : 'Remove tags from'} ${formatNumber(count)} selected ${noun}.`}
    >
      {open && <BulkTagForm mode={mode} contactIds={contactIds} onClose={() => onOpenChange(false)} onDone={onDone} />}
    </Dialog>
  )
}

function BulkTagForm({ mode, contactIds, onClose, onDone }: Omit<BulkTagDialogProps, 'open' | 'onOpenChange'> & { onClose: () => void }) {
  const { tags, isLoading } = useTags()
  const invalidate = useInvalidateContacts()
  const { toast } = useToast()
  const [tagIds, setTagIds] = useState<string[]>([])
  const [error, setError] = useState<string>()
  const [pickerError, setPickerError] = useState<string>()
  const [saving, setSaving] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!tagIds.length) {
      setPickerError('Choose at least one tag.')
      return
    }
    setSaving(true)
    setError(undefined)
    try {
      const result = await unwrap(
        api.POST('/api/v1/contacts/bulk-tag/', {
          body: { contact_ids: [...contactIds], ...(mode === 'add' ? { add_tag_ids: tagIds } : { remove_tag_ids: tagIds }) },
        }),
      )
      void invalidate()
      const changed = mode === 'add' ? result.added : result.removed
      toast({
        title: mode === 'add' ? 'Tags added' : 'Tags removed',
        description: `${formatNumber(changed)} tag ${changed === 1 ? 'change' : 'changes'} across ${formatNumber(result.contact_count)} ${result.contact_count === 1 ? 'contact' : 'contacts'}.`,
        tone: 'success',
      })
      onDone()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <FormError message={error} />
      <Field label="Tags" required error={pickerError}>
        <TagPicker
          tags={tags}
          value={tagIds}
          loading={isLoading}
          onChange={(value) => {
            setTagIds(value)
            setPickerError(undefined)
          }}
        />
      </Field>
      <div className="-mx-5 -mb-4 mt-1 flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">
        <Button variant="secondary" onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" variant={mode === 'remove' ? 'danger' : 'primary'} loading={saving}>
          {mode === 'add' ? 'Add tags' : 'Remove tags'}
        </Button>
      </div>
    </form>
  )
}
