import { zodResolver } from '@hookform/resolvers/zod'
import { Plus, Trash2 } from 'lucide-react'
import { useId } from 'react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'
import { z } from 'zod'
import { api, unwrap } from '../../../../api/client'
import { applyApiErrorToForm, isApiError } from '../../../../api/errors'
import { Button, Dialog, Field, Input, useToast } from '../../../../components/app'
import { useInvalidateContacts, useTags } from '../api'
import { isValidE164, normalizePhoneInput } from '../lib/phone'
import type { Contact } from '../lib/types'
import { FormError, TagPicker } from './shared'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const MAX_ATTRIBUTES = 100

const schema = z
  .object({
    phone: z
      .string()
      .trim()
      .min(1, 'Enter a phone number.')
      .refine((value) => isValidE164(normalizePhoneInput(value)), 'Enter a valid number with its country code, e.g. +91 98765 43210.'),
    name: z.string().trim().max(255, 'Use at most 255 characters.'),
    email: z
      .string()
      .trim()
      .refine((value) => !value || EMAIL_RE.test(value), 'Enter a valid email address.'),
    tags: z.array(z.string()),
    attributes: z.array(z.object({ key: z.string().trim().max(64, 'Use at most 64 characters.'), value: z.string() })).max(MAX_ATTRIBUTES),
  })
  .superRefine((values, ctx) => {
    const seen = new Set<string>()
    values.attributes.forEach((attribute, index) => {
      if (!attribute.key && attribute.value.trim()) {
        ctx.addIssue({ code: 'custom', path: ['attributes', index, 'key'], message: 'Add a name for this value.' })
      }
      if (attribute.key && seen.has(attribute.key)) {
        ctx.addIssue({ code: 'custom', path: ['attributes', index, 'key'], message: 'This name is already used.' })
      }
      if (attribute.key) seen.add(attribute.key)
    })
  })

type FormValues = z.infer<typeof schema>

const displayValue = (value: unknown) => (typeof value === 'string' ? value : JSON.stringify(value))

type ContactFormDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Edit this contact; omit to create one. */
  contact?: Contact
  onSaved?: (contact: Contact) => void
}

export function ContactFormDialog({ open, onOpenChange, contact, onSaved }: ContactFormDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={contact ? 'Edit contact' : 'Add contact'}
      description={contact ? undefined : 'Add someone you can message on WhatsApp. Marketing consent is recorded separately.'}
    >
      {open && <ContactForm contact={contact} onCancel={() => onOpenChange(false)} onSaved={onSaved} />}
    </Dialog>
  )
}

function ContactForm({ contact, onCancel, onSaved }: { contact?: Contact; onCancel: () => void; onSaved?: (contact: Contact) => void }) {
  const { tags, isLoading: tagsLoading } = useTags()
  const invalidate = useInvalidateContacts()
  const { toast } = useToast()
  const formId = useId()

  const originalAttributes = contact?.attributes ?? {}
  const {
    control,
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      phone: contact?.phone_e164 ?? '',
      name: contact?.name ?? '',
      email: contact?.email ?? '',
      tags: contact?.tags ?? [],
      attributes: Object.entries(originalAttributes).map(([key, value]) => ({ key, value: displayValue(value) })),
    },
  })
  const attributes = useFieldArray({ control, name: 'attributes' })

  const onSubmit = handleSubmit(async (values) => {
    const attributeBody: Record<string, unknown> = {}
    for (const { key, value } of values.attributes) {
      if (!key) continue
      // Keep non-string values (numbers, lists) as they were when their text wasn't changed.
      const original = originalAttributes[key]
      attributeBody[key] = original !== undefined && displayValue(original) === value ? original : value
    }
    const body = {
      phone_e164: normalizePhoneInput(values.phone),
      name: values.name,
      email: values.email,
      tags: values.tags,
      attributes: attributeBody,
    }
    try {
      const saved = contact
        ? await unwrap(api.PATCH('/api/v1/contacts/{id}/', { params: { path: { id: contact.id } }, body }))
        : await unwrap(api.POST('/api/v1/contacts/', { body }))
      void invalidate()
      toast({ title: contact ? 'Contact saved' : 'Contact added', tone: 'success' })
      onSaved?.(saved)
      onCancel()
    } catch (error) {
      if (isApiError(error, 'conflict')) {
        setError('phone', { type: 'server', message: error.message }, { shouldFocus: true })
        return
      }
      applyApiErrorToForm(error, setError, { fieldMap: { phone_e164: 'phone' }, fields: ['phone', 'name', 'email', 'tags'] })
    }
  })

  return (
    <form id={formId} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <FormError message={errors.root?.server?.message} />
      <Field
        label="WhatsApp phone number"
        required
        error={errors.phone?.message}
        hint="Include the country code. 10-digit Indian mobile numbers get +91 added."
      >
        <Input type="tel" inputMode="tel" autoComplete="tel" placeholder="+91 98765 43210" {...register('phone')} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" error={errors.name?.message}>
          <Input autoComplete="name" {...register('name')} />
        </Field>
        <Field label="Email" error={errors.email?.message}>
          <Input type="email" autoComplete="email" {...register('email')} />
        </Field>
      </div>
      <Field label="Tags" error={errors.tags?.message}>
        <Controller
          control={control}
          name="tags"
          render={({ field }) => <TagPicker tags={tags} value={field.value} onChange={field.onChange} loading={tagsLoading} />}
        />
      </Field>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-[13px] font-medium text-ink">Custom attributes</legend>
        <p className="text-[13px] text-muted">Extra details such as city or last order. Campaigns can use them as template variables.</p>
        {attributes.fields.map((item, index) => (
          <div key={item.id} className="grid grid-cols-[1fr_1fr_auto] items-start gap-2">
            <Field label={`Attribute ${index + 1} name`} hideLabel error={errors.attributes?.[index]?.key?.message}>
              <Input placeholder="city" {...register(`attributes.${index}.key`)} />
            </Field>
            <Field label={`Attribute ${index + 1} value`} hideLabel>
              <Input placeholder="Jaipur" {...register(`attributes.${index}.value`)} />
            </Field>
            <Button variant="ghost" size="icon" aria-label={`Remove attribute ${index + 1}`} onClick={() => attributes.remove(index)}>
              <Trash2 className="size-4" aria-hidden="true" />
            </Button>
          </div>
        ))}
        {attributes.fields.length < MAX_ATTRIBUTES && (
          <div>
            <Button variant="secondary" size="sm" icon={<Plus className="size-3.5" aria-hidden="true" />} onClick={() => attributes.append({ key: '', value: '' })}>
              Add attribute
            </Button>
          </div>
        )}
      </fieldset>

      <div className="-mx-5 -mb-4 mt-1 flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">
        <Button variant="secondary" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="submit" loading={isSubmitting}>
          {contact ? 'Save contact' : 'Add contact'}
        </Button>
      </div>
    </form>
  )
}
