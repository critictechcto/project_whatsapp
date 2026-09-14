import { useState } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'
import { Field, Select, Skeleton, templatePreview, templateVariables, WhatsAppMessagePreview } from '../../../../components/app'
import { errorMessage } from '../../../../api/errors'
import { useWorkspace } from '../../../../lib/workspace'
import { Notice } from '../components/Notice'
import { VariableSourceFields } from '../components/VariableSourceFields'
import { previewValues, type SampleContact } from '../variables'
import type { WizardValues } from '../wizardSchema'
import { useContactOptions, useTemplate } from './queries'

export function PersonaliseStep() {
  const {
    control,
    formState: { errors },
  } = useFormContext<WizardValues>()
  const { workspaceId } = useWorkspace()
  const templateId = useWatch({ control, name: 'template_id' })
  const mapping = useWatch({ control, name: 'variable_mapping' })
  const template = useTemplate(workspaceId, templateId || undefined)
  const contacts = useContactOptions(workspaceId, '')
  const [sampleId, setSampleId] = useState('')

  if (template.isError) return <Notice tone="error">{errorMessage(template.error)}</Notice>
  if (!template.data) return <Skeleton className="h-48 w-full" />

  const spec = templateVariables(template.data)
  const found = contacts.data?.find((contact) => contact.id === sampleId) ?? contacts.data?.[0]
  const sample: SampleContact | null = found
    ? {
        name: found.name,
        phone_e164: found.phone_e164,
        email: found.email,
        attributes: found.attributes,
      }
    : null
  const mappingErrors = errors.variable_mapping
  const hasVariables = spec.header.names.length > 0 || spec.body.names.length > 0 || spec.buttons.length > 0
  const toMessages = (error: { value?: { message?: string }; fallback?: { message?: string } } | undefined) => ({
    value: error?.value?.message,
    fallback: error?.fallback?.message,
  })

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex flex-col gap-4">
        {!hasVariables ? (
          <Notice title="Nothing to fill in">This template has no variables. Every contact receives the same message.</Notice>
        ) : (
          <p className="text-sm text-muted">
            Choose where each placeholder gets its value. The fallback is sent when a contact has no value, since Meta rejects empty
            parameters.
          </p>
        )}

        {spec.header.names.length > 0 && (
          <Controller
            control={control}
            name="variable_mapping.header"
            render={({ field }) => (
              <VariableSourceFields
                label={`Header {{${spec.header.names[0]}}}`}
                value={field.value}
                onChange={field.onChange}
                example={spec.header.examples[0]}
                errors={toMessages(mappingErrors?.header ?? undefined)}
              />
            )}
          />
        )}

        {spec.body.names.map((name, index) => (
          <Controller
            key={`body-${name}`}
            control={control}
            name={`variable_mapping.body.${index}`}
            render={({ field }) => (
              <VariableSourceFields
                label={`Body {{${name}}}`}
                value={field.value}
                onChange={field.onChange}
                example={spec.body.examples[index]}
                errors={toMessages(mappingErrors?.body?.[index])}
              />
            )}
          />
        ))}

        {spec.buttons.map((button, index) => (
          <Controller
            key={`button-${button.index}`}
            control={control}
            name={`variable_mapping.buttons.${index}.source`}
            render={({ field }) => (
              <VariableSourceFields
                label={`Button “${button.text}” {{${button.names[0] ?? '1'}}}`}
                value={field.value}
                onChange={field.onChange}
                example={button.example}
                errors={toMessages(mappingErrors?.buttons?.[index]?.source)}
              />
            )}
          />
        ))}
      </div>

      <aside aria-labelledby="personalise-preview-heading" className="flex h-fit flex-col gap-3">
        <h3 id="personalise-preview-heading" className="font-display text-base font-semibold text-ink">
          Preview
        </h3>
        <Field label="Preview for" hint="A contact from your list, to check how values fill in.">
          <Select
            value={found?.id ?? ''}
            onChange={(event) => setSampleId(event.target.value)}
            options={(contacts.data ?? []).map((contact) => ({ value: contact.id, label: contact.name || contact.phone_e164 }))}
            placeholder={contacts.data?.length ? undefined : 'No contacts yet'}
          />
        </Field>
        <WhatsAppMessagePreview message={templatePreview(template.data, previewValues(mapping, sample))} framed />
      </aside>
    </div>
  )
}
