import { useState } from 'react'
import type { MessageTemplate } from '../../../../api/types'
import { Button } from '../../../../components/app/Button'
import { Dialog } from '../../../../components/app/Dialog'
import { Field } from '../../../../components/app/Field'
import {
  emptyVariableValues,
  templatePreview,
  toSendParams,
  variablesComplete,
  type TemplateVariableValues,
} from '../../../../components/app/whatsapp/template'
import { TemplatePicker } from '../../../../components/app/whatsapp/TemplatePicker'
import { TemplateVariableForm } from '../../../../components/app/whatsapp/TemplateVariableForm'
import type { Conversation, SendMessageRequest } from '../api'
import type { OutboxDisplay } from '../hooks/thread'
import { contactName } from '../utils'

type TemplateDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  conversation: Conversation
  onSend: (request: SendMessageRequest, display: OutboxDisplay) => void
}

/** Pick an approved template, fill its variables with a live preview, and send it. */
export function TemplateDialog({ open, onOpenChange, conversation, onSend }: TemplateDialogProps) {
  const [template, setTemplate] = useState<MessageTemplate | null>(null)
  const [values, setValues] = useState<TemplateVariableValues>(emptyVariableValues)
  const [error, setError] = useState<string | null>(null)

  const close = () => {
    setTemplate(null)
    setValues(emptyVariableValues)
    setError(null)
    onOpenChange(false)
  }

  const needsOptIn = template?.category === 'MARKETING' && conversation.contact.marketing_opt_in_status !== 'opted_in'

  const submit = () => {
    if (!template) {
      setError('Choose a template to send.')
      return
    }
    if (!variablesComplete(template, values)) {
      setError('Fill in every variable before sending.')
      return
    }
    onSend(
      { type: 'template', template_id: template.id, preview_url: false, ...toSendParams(values) },
      { type: 'template', text: templatePreview(template, values).body, templateName: template.name },
    )
    close()
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      size="lg"
      title="Send a template"
      description="Templates approved by Meta can be sent at any time, including after the 24-hour customer service window closes."
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button onClick={submit}>Send template</Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <Field label="Template">
          <TemplatePicker
            value={template?.id ?? null}
            showPreview={false}
            onChange={(next) => {
              setTemplate(next)
              setValues(emptyVariableValues)
              setError(null)
            }}
          />
        </Field>
        {template && <TemplateVariableForm template={template} value={values} onChange={setValues} />}
        {needsOptIn && (
          <p role="note" className="rounded-md bg-amber-soft px-3 py-2 text-[13px] text-amber">
            This is a marketing template and {contactName(conversation.contact)} has no recorded marketing opt-in, so it will likely be
            blocked. Utility templates don't need marketing opt-in.
          </p>
        )}
        {error && (
          <p role="alert" className="text-[13px] text-signal">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  )
}
