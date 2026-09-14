import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button, Checkbox, Dialog, useToast } from '../../../../components/app'
import { useWorkspace } from '../../../../lib/workspace'
import { orderKeys, orderMutations, storeOrder, type Order } from '../api'
import { actionLabels, availableOrderActions, progressActions, simpleActionCopy, type OrderAction, type SimpleAction } from '../actions'
import { orderActionError } from '../labels'
import { CancelDialog } from './CancelDialog'
import { ShipDialog } from './ShipDialog'

type OrderActionsProps = {
  order: Order
  /** A readable error for the page, e.g. a 409 `invalid_order_transition`. */
  onError: (message: string) => void
  onSuccess: () => void
}

function runSimple(order: Order, action: SimpleAction, notify: boolean): Promise<Order> {
  if (action === 'cod') return orderMutations.markCodCollected(order.id)
  if (action === 'refund') return orderMutations.markRefunded(order.id)
  return orderMutations.transition(order.id, { to_status: action, notify_buyer: notify })
}

function SimpleActionDialog({
  order,
  action,
  onClose,
  onDone,
  onFailed,
}: {
  order: Order
  action: SimpleAction
  onClose: () => void
  onDone: (order: Order, message: string) => void
  onFailed: (error: unknown) => void
}) {
  const copy = simpleActionCopy(action, order)
  const [notify, setNotify] = useState(true)
  const mutation = useMutation({
    mutationFn: () => runSimple(order, action, notify),
    onSuccess: (updated) => onDone(updated, copy.success),
    onError: onFailed,
  })

  return (
    <Dialog
      size="sm"
      open
      onOpenChange={(open) => {
        if (!open && !mutation.isPending) onClose()
      }}
      dismissible={!mutation.isPending}
      title={copy.title}
      description={copy.description}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>
            Go back
          </Button>
          <Button loading={mutation.isPending} onClick={() => mutation.mutate()}>
            {copy.confirm}
          </Button>
        </>
      }
    >
      {copy.notify && (
        <Checkbox label="Notify the buyer on WhatsApp" checked={notify} onChange={(event) => setNotify(event.target.checked)} />
      )}
    </Dialog>
  )
}

/** Header buttons for the order, driven by `allowed_transitions` and the member's role, with their dialogs. */
export function OrderActions({ order, onError, onSuccess }: OrderActionsProps) {
  const { workspaceId, can } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [open, setOpen] = useState<OrderAction | null>(null)
  const actions = availableOrderActions(order, can)
  const primary = actions.find((action) => progressActions.includes(action))

  const close = () => setOpen(null)

  const done = (updated: Order, message: string) => {
    storeOrder(queryClient, workspaceId, updated)
    setOpen(null)
    onSuccess()
    toast({ title: message, tone: 'success' })
  }

  const failed = (error: unknown) => {
    setOpen(null)
    onError(orderActionError(error))
    void queryClient.invalidateQueries({ queryKey: orderKeys.detail(workspaceId, order.id) })
    void queryClient.invalidateQueries({ queryKey: orderKeys.lists(workspaceId) })
  }

  if (actions.length === 0) return null

  return (
    <>
      {actions.map((action) => (
        <Button key={action} variant={action === primary ? 'primary' : 'secondary'} onClick={() => setOpen(action)}>
          {actionLabels[action]}
        </Button>
      ))}

      {open === 'shipped' && <ShipDialog order={order} onClose={close} onShipped={(updated) => done(updated, 'Marked shipped')} onFailed={failed} />}
      {open === 'cancel' && <CancelDialog order={order} onClose={close} onCancelled={(updated) => done(updated, 'Order cancelled')} onFailed={failed} />}
      {open && open !== 'shipped' && open !== 'cancel' && (
        <SimpleActionDialog order={order} action={open} onClose={close} onDone={done} onFailed={failed} />
      )}
    </>
  )
}
