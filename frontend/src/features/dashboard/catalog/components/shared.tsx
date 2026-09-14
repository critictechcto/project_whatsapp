import { CircleAlert, Info } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button, Dialog } from '../../../../components/app'
import { cn } from '../../../../lib/cn'

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

/** A quiet information panel. */
export function Note({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-start gap-2 rounded-lg border border-line-2 bg-paper/60 px-3 py-2.5 text-[13px] text-ink-2', className)}>
      <Info className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden="true" />
      <div className="min-w-0">{children}</div>
    </div>
  )
}

/** "12/24" counter for WhatsApp length limits; turns red past the limit. */
export function CharCount({ value, max }: { value: string; max: number }) {
  const over = value.length > max
  return (
    <span className={cn('font-mono text-[12px]', over ? 'text-signal' : 'text-muted')}>
      {value.length}/{max}
      <span className="sr-only"> characters{over ? `, ${value.length - max} over the limit` : ''}</span>
    </span>
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
