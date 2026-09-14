import { useMemo, useState } from 'react'
import { Button } from '../../../../components/app/Button'
import { Combobox } from '../../../../components/app/Combobox'
import { Dialog } from '../../../../components/app/Dialog'
import { Field } from '../../../../components/app/Field'
import { statusInfo } from '../../../../components/app/status'
import { toSendError } from '../api'
import { useContactSearch, useStartConversation } from '../hooks/conversations'
import { useDebouncedValue } from '../hooks/misc'
import { formatPhone } from '../utils'

type StartConversationDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onStarted: (conversationId: string) => void
}

/** Opens (or creates) the conversation with a contact. */
export function StartConversationDialog({ open, onOpenChange, onStarted }: StartConversationDialogProps) {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 250)
  const [contactId, setContactId] = useState<string | null>(null)
  const [selectedLabels, setSelectedLabels] = useState<Record<string, string>>({})
  const contacts = useContactSearch(debouncedSearch, open)
  const start = useStartConversation()

  const options = useMemo(
    () =>
      (contacts.data ?? []).map((contact) => ({
        value: contact.id,
        label: contact.name || formatPhone(contact.phone_e164),
        description: `${formatPhone(contact.phone_e164)} · ${statusInfo(contact.marketing_opt_in_status).label}`,
      })),
    [contacts.data],
  )

  const close = () => {
    setSearch('')
    setContactId(null)
    start.reset()
    onOpenChange(false)
  }

  const submit = () => {
    if (!contactId) return
    start.mutate(contactId, {
      onSuccess: (conversation) => {
        close()
        onStarted(conversation.id)
      },
    })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title="New conversation"
      description="Pick a contact to open their conversation. Until they write to you, WhatsApp only allows approved templates."
      dismissible={!start.isPending}
      footer={
        <>
          <Button variant="secondary" onClick={close} disabled={start.isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!contactId} loading={start.isPending}>
            Open conversation
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label="Contact">
          <Combobox
            options={options}
            value={contactId}
            onChange={(value) => {
              setContactId(value)
              const option = options.find((candidate) => candidate.value === value)
              if (option) setSelectedLabels((labels) => ({ ...labels, [option.value]: option.label }))
            }}
            onSearchChange={setSearch}
            filter={false}
            loading={contacts.isFetching}
            placeholder="Search by name or phone"
            emptyText="No contacts found"
            selectedLabels={selectedLabels}
          />
        </Field>
        {start.isError && (
          <p role="alert" className="text-[13px] text-signal">
            {toSendError(start.error).message}
          </p>
        )}
      </div>
    </Dialog>
  )
}
