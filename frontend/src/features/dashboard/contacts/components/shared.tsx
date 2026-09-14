import { CircleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button, Combobox, Dialog, StatusBadge, Tooltip } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { optInInfo } from '../lib/consent'
import type { OptInStatus, Tag } from '../lib/types'

/** Form-level error (react-hook-form `errors.root.server`). */
export function FormError({ message }: { message: string | undefined }) {
  if (!message) return null
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-signal/25 bg-signal-soft/60 px-3 py-2.5 text-sm text-signal">
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  )
}

/** Marketing opt-in badge; the explanation is in a tooltip and also read by screen readers. */
export function OptInBadge({ status }: { status: OptInStatus }) {
  const info = optInInfo[status]
  return (
    <Tooltip content={info.explanation}>
      <span tabIndex={0} className="rounded-full focus-visible:outline-2 focus-visible:outline-accent">
        <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
        <span className="sr-only">. {info.explanation}</span>
      </span>
    </Tooltip>
  )
}

export function TagChip({ tag, className }: { tag: Pick<Tag, 'name' | 'color'>; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex h-6 max-w-40 items-center gap-1.5 rounded-md border border-line-2 bg-paper/70 px-2 text-[12px] text-ink-2',
        className,
      )}
    >
      <span aria-hidden="true" className="size-2 shrink-0 rounded-full bg-muted/50" style={tag.color ? { backgroundColor: tag.color } : undefined} />
      <span className="truncate">{tag.name}</span>
    </span>
  )
}

/** Tag chips for a list of tag ids; unknown ids are skipped. */
export function TagList({ tagIds, tagMap, max, empty = null }: { tagIds: readonly string[]; tagMap: Map<string, Tag>; max?: number; empty?: ReactNode }) {
  const tags = tagIds.map((id) => tagMap.get(id)).filter((tag): tag is Tag => Boolean(tag))
  if (!tags.length) return <>{empty}</>
  const shown = max ? tags.slice(0, max) : tags
  const hidden = tags.length - shown.length
  return (
    <ul className="flex flex-wrap gap-1" aria-label="Tags">
      {shown.map((tag) => (
        <li key={tag.id}>
          <TagChip tag={tag} />
        </li>
      ))}
      {hidden > 0 && (
        <li className="inline-flex h-6 items-center px-1 font-mono text-[11px] text-muted" title={tags.slice(shown.length).map((t) => t.name).join(', ')}>
          +{hidden}
        </li>
      )}
    </ul>
  )
}

type TagPickerProps = {
  tags: readonly Tag[]
  value: readonly string[]
  onChange: (value: string[]) => void
  placeholder?: string
  loading?: boolean
  disabled?: boolean
  'aria-label'?: string
  className?: string
}

/** Multi-select of workspace tags. Works inside `<Field>` or with its own `aria-label`. */
export function TagPicker({ tags, value, onChange, placeholder = 'Choose tags', ...rest }: TagPickerProps) {
  return (
    <Combobox
      multiple
      options={tags.map((tag) => ({ value: tag.id, label: tag.name }))}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      emptyText="No tags match"
      {...rest}
    />
  )
}

type ConfirmDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  confirmLabel: string
  onConfirm: () => void
  loading?: boolean
  danger?: boolean
}

export function ConfirmDialog({ open, onOpenChange, title, description, children, confirmLabel, onConfirm, loading, danger }: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="sm"
      title={title}
      description={description}
      dismissible={!loading}
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>
            Cancel
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  )
}
