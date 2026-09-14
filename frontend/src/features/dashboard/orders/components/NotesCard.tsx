import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { errorMessage } from '../../../../api/errors'
import { Button, Field, Textarea, useToast } from '../../../../components/app'
import { useWorkspace } from '../../../../lib/workspace'
import { orderMutations, storeOrder, type Order } from '../api'
import { SectionCard } from './SectionCard'

const MAX_NOTES = 2000

/** Seller-internal notes. Render with `key={order.notes}` so a saved or refetched value resets the draft. */
export function NotesCard({ order }: { order: Order }) {
  const { workspaceId, can } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [draft, setDraft] = useState(order.notes)
  const canEdit = can('agent')

  const save = useMutation({
    mutationFn: (notes: string) => orderMutations.updateNotes(order.id, notes),
    onSuccess: (updated) => {
      storeOrder(queryClient, workspaceId, updated)
      toast({ title: 'Notes saved', tone: 'success' })
    },
  })

  if (!canEdit) {
    return (
      <SectionCard title="Notes">
        {order.notes ? <p className="whitespace-pre-wrap text-sm text-ink">{order.notes}</p> : <p className="text-sm text-muted">No notes.</p>}
      </SectionCard>
    )
  }

  const tooLong = draft.length > MAX_NOTES
  const error = tooLong ? `Keep notes under ${MAX_NOTES} characters.` : save.isError ? errorMessage(save.error) : undefined

  return (
    <SectionCard title="Notes">
      <form
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          if (!tooLong) save.mutate(draft)
        }}
      >
        <Field label="Notes for your team" hint="Buyers never see these." error={error}>
          <Textarea rows={4} value={draft} onChange={(event) => setDraft(event.target.value)} />
        </Field>
        <div className="flex items-center justify-between gap-3">
          <span className="font-mono text-[12px] text-muted" aria-live="polite">
            {draft.length}/{MAX_NOTES}
          </span>
          <Button type="submit" size="sm" variant="secondary" loading={save.isPending} disabled={draft === order.notes || tooLong}>
            Save notes
          </Button>
        </div>
      </form>
    </SectionCard>
  )
}
