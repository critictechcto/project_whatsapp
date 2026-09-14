import type { ReactNode } from 'react'
import { Button, Dialog } from '../../../../components/app'

type ConfirmDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  confirmLabel: string
  onConfirm: () => void
  loading?: boolean
  danger?: boolean
  children?: ReactNode
}

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, onConfirm, loading, danger, children }: ConfirmDialogProps) {
  return (
    <Dialog
      size="sm"
      open={open}
      onOpenChange={onOpenChange}
      dismissible={!loading}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>
            Go back
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  )
}
