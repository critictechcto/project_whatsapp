import type { ReactNode } from 'react'
import { Button, Dialog } from '../../../../components/app'

type ConfirmDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  confirmLabel: string
  cancelLabel?: string
  tone?: 'primary' | 'danger'
  loading?: boolean
  confirmDisabled?: boolean
  onConfirm: () => void
}

/** Confirmation dialog for destructive or important actions. Candidate for `components/app`. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  confirmLabel,
  cancelLabel = 'Cancel',
  tone = 'danger',
  loading = false,
  confirmDisabled = false,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!loading) onOpenChange(next)
      }}
      dismissible={!loading}
      size="sm"
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={tone} loading={loading} disabled={confirmDisabled} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  )
}
