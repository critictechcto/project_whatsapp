import { ArrowDown, ArrowUp, GripVertical } from 'lucide-react'
import { useState, type DragEvent } from 'react'
import { errorMessage } from '../../../../api/errors'
import { Button, Dialog, Skeleton } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { moveItem } from '../lib/reorder'
import { FormError } from './shared'

export type ReorderItem = { id: string; label: string; detail?: string }

type ReorderDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  items: readonly ReorderItem[] | undefined
  loading?: boolean
  onSave: (ids: string[]) => Promise<void>
}

export function ReorderDialog(props: ReorderDialogProps) {
  const { open, onOpenChange, title, description } = props
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={title} description={description}>
      {open && <ReorderList {...props} />}
    </Dialog>
  )
}

/**
 * Drag rows, or use the move buttons (keyboard and screen readers). Each move is announced.
 * Saving sends the full ordering.
 */
function ReorderList({ items, loading, onSave, onOpenChange }: ReorderDialogProps) {
  const [order, setOrder] = useState<ReorderItem[] | null>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()

  const rows = order ?? (items ? [...items] : [])
  const changed = order !== null && order.some((item, index) => item.id !== items?.[index]?.id)

  const move = (from: number, to: number) => {
    if (to < 0 || to >= rows.length || from === to) return
    const next = moveItem(rows, from, to)
    setOrder(next)
    setAnnouncement(`${rows[from].label} moved to position ${to + 1} of ${rows.length}.`)
  }

  const onDrop = (event: DragEvent<HTMLLIElement>, index: number) => {
    event.preventDefault()
    if (dragIndex !== null) move(dragIndex, index)
    setDragIndex(null)
  }

  const save = async () => {
    setSaving(true)
    setError(undefined)
    try {
      await onSave(rows.map((row) => row.id))
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err))
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <FormError message={error} />
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
      {loading && !items ? (
        <div aria-busy="true" className="flex flex-col gap-2">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </div>
      ) : (
        <ol aria-label="Order" className="flex flex-col gap-1.5">
          {rows.map((row, index) => (
            <li
              key={row.id}
              draggable
              onDragStart={(event) => {
                setDragIndex(index)
                event.dataTransfer.effectAllowed = 'move'
              }}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => onDrop(event, index)}
              onDragEnd={() => setDragIndex(null)}
              className={cn(
                'flex items-center gap-2 rounded-lg border border-line-2 bg-card py-1.5 pl-2 pr-1.5',
                dragIndex === index && 'opacity-50',
              )}
            >
              <GripVertical className="size-4 shrink-0 cursor-grab text-muted" aria-hidden="true" />
              <span className="w-6 shrink-0 text-right font-mono text-[12px] text-muted">{index + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink">{row.label}</span>
                {row.detail && <span className="block truncate font-mono text-[11.5px] text-muted">{row.detail}</span>}
              </span>
              <Button variant="ghost" size="icon-sm" aria-label={`Move ${row.label} up`} disabled={index === 0} onClick={() => move(index, index - 1)}>
                <ArrowUp className="size-4" aria-hidden="true" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Move ${row.label} down`}
                disabled={index === rows.length - 1}
                onClick={() => move(index, index + 1)}
              >
                <ArrowDown className="size-4" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ol>
      )}
      <div className="-mx-5 -mb-4 mt-1 flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">
        <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={saving}>
          Cancel
        </Button>
        <Button onClick={() => void save()} loading={saving} disabled={!changed}>
          Save order
        </Button>
      </div>
    </div>
  )
}
