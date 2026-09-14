import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { api, unwrap } from '../../../../api/client'
import { applyApiErrorToForm } from '../../../../api/errors'
import { Button, Dialog, Field, Textarea, useToast } from '../../../../components/app'
import { useInvalidateContacts } from '../api'
import type { Contact } from '../lib/types'
import { FormError } from './shared'

type ConsentDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  contact: Contact
  action: 'opt_in' | 'opt_out'
}

const optInSchema = z.object({ evidence: z.string().trim().min(1, 'Describe how the customer opted in.').max(2000, 'Use at most 2000 characters.') })
const optOutSchema = z.object({ evidence: z.string().trim().max(2000, 'Use at most 2000 characters.') })

type Values = { evidence: string }

/** Records a manual marketing opt-in or opt-out (`source: manual`). */
export function ConsentDialog({ open, onOpenChange, contact, action }: ConsentDialogProps) {
  const optIn = action === 'opt_in'
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={optIn ? 'Record marketing opt-in' : 'Record marketing opt-out'}
      description={
        optIn
          ? 'Only record an opt-in the customer actually gave, such as a signed form, a website checkbox or a WhatsApp message asking for offers.'
          : 'Campaigns will skip this contact for marketing messages until a new opt-in is recorded, for example if they send START.'
      }
    >
      {open && <ConsentForm contact={contact} action={action} onClose={() => onOpenChange(false)} />}
    </Dialog>
  )
}

function ConsentForm({ contact, action, onClose }: { contact: Contact; action: 'opt_in' | 'opt_out'; onClose: () => void }) {
  const optIn = action === 'opt_in'
  const invalidate = useInvalidateContacts()
  const { toast } = useToast()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(optIn ? optInSchema : optOutSchema), defaultValues: { evidence: '' } })

  const onSubmit = handleSubmit(async ({ evidence }) => {
    const options = { params: { path: { id: contact.id } }, body: { source: 'manual' as const, evidence } }
    try {
      if (optIn) await unwrap(api.POST('/api/v1/contacts/{id}/opt-in/', options))
      else await unwrap(api.POST('/api/v1/contacts/{id}/opt-out/', options))
      void invalidate()
      toast({ title: optIn ? 'Opt-in recorded' : 'Opt-out recorded', tone: 'success' })
      onClose()
    } catch (error) {
      applyApiErrorToForm(error, setError, { fields: ['evidence'] })
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <FormError message={errors.root?.server?.message} />
      <Field
        label={optIn ? 'How did they opt in?' : 'Note'}
        required={optIn}
        error={errors.evidence?.message}
        hint={optIn ? 'Saved in the consent history as evidence, with your name and the time.' : 'Optional. For example, "Asked on a call to stop offers".'}
      >
        <Textarea rows={3} {...register('evidence')} />
      </Field>
      <div className="-mx-5 -mb-4 mt-1 flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">
        <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="submit" variant={optIn ? 'primary' : 'danger'} loading={isSubmitting}>
          {optIn ? 'Record opt-in' : 'Record opt-out'}
        </Button>
      </div>
    </form>
  )
}
