import type { FieldPath } from 'react-hook-form'
import { z } from 'zod'
import type { Campaign, CampaignWrite } from './api'
import { contactFieldValues, mappingFromApi, mappingToApi } from './variables'

export const variableSourceSchema = z
  .object({
    source: z.enum(['contact_field', 'attribute', 'static']),
    value: z.string(),
    fallback: z.string(),
  })
  .superRefine((source, ctx) => {
    if (source.source === 'static' && !source.value.trim()) {
      ctx.addIssue({ code: 'custom', path: ['value'], message: 'Enter the text to send.' })
    }
    if (source.source === 'attribute' && !source.value.trim()) {
      ctx.addIssue({ code: 'custom', path: ['value'], message: 'Enter an attribute key, for example city.' })
    }
    if (source.source === 'contact_field' && !contactFieldValues.includes(source.value)) {
      ctx.addIssue({ code: 'custom', path: ['value'], message: 'Choose a contact field.' })
    }
    if (source.source !== 'static' && !source.fallback.trim()) {
      // Meta rejects empty parameters, so contacts without the value need something to send.
      ctx.addIssue({ code: 'custom', path: ['fallback'], message: 'Add a fallback for contacts without this value.' })
    }
  })

const mappingSchema = z.object({
  header: variableSourceSchema.nullable(),
  body: z.array(variableSourceSchema),
  buttons: z.array(z.object({ index: z.string(), source: variableSourceSchema })),
})

export const wizardSchema = z.object({
  name: z.string().trim().min(1, 'Give the campaign a name.').max(120, 'Use 120 characters or fewer.'),
  template_id: z.string().min(1, 'Choose an approved template.'),
  audience: z
    .object({
      tag_ids: z.array(z.string()),
      match: z.enum(['any', 'all']),
      contact_ids: z.array(z.string()),
    })
    .superRefine((audience, ctx) => {
      if (!audience.tag_ids.length && !audience.contact_ids.length) {
        ctx.addIssue({ code: 'custom', path: ['tag_ids'], message: 'Choose at least one tag or contact.' })
      }
    }),
  variable_mapping: mappingSchema,
  schedule: z
    .object({ mode: z.enum(['now', 'later']), at: z.string().nullable() })
    .superRefine((schedule, ctx) => {
      if (schedule.mode !== 'later') return
      if (!schedule.at) {
        ctx.addIssue({ code: 'custom', path: ['at'], message: 'Pick a date and time.' })
      } else if (new Date(schedule.at).getTime() <= Date.now()) {
        ctx.addIssue({ code: 'custom', path: ['at'], message: 'Choose a time in the future.' })
      }
    }),
  consent: z.boolean().refine((value) => value, {
    message: 'Confirm that these contacts agreed to receive WhatsApp messages from you.',
  }),
})

export type WizardValues = z.infer<typeof wizardSchema>

export type WizardStep = {
  id: 'template' | 'audience' | 'personalise' | 'schedule' | 'review'
  label: string
  title: string
  fields: readonly FieldPath<WizardValues>[]
}

export const wizardSteps: readonly WizardStep[] = [
  { id: 'template', label: 'Template', title: 'Choose a template', fields: ['name', 'template_id'] },
  { id: 'audience', label: 'Audience', title: 'Choose who receives it', fields: ['audience'] },
  { id: 'personalise', label: 'Personalise', title: 'Fill in the variables', fields: ['variable_mapping'] },
  { id: 'schedule', label: 'Schedule', title: 'Choose when to send', fields: ['schedule'] },
  { id: 'review', label: 'Review', title: 'Review and launch', fields: ['consent'] },
]

export function valuesFromCampaign(campaign: Campaign | null): WizardValues {
  return {
    name: campaign?.name ?? '',
    template_id: campaign?.template.id ?? '',
    audience: {
      tag_ids: [...(campaign?.audience.tag_ids ?? [])],
      match: campaign?.audience.match ?? 'any',
      contact_ids: [...(campaign?.audience.contact_ids ?? [])],
    },
    variable_mapping: mappingFromApi(campaign?.variable_mapping),
    schedule: { mode: campaign?.scheduled_at ? 'later' : 'now', at: campaign?.scheduled_at ?? null },
    consent: false,
  }
}

export function writeBody(values: WizardValues): CampaignWrite {
  return {
    name: values.name.trim(),
    template_id: values.template_id,
    audience: values.audience,
    variable_mapping: mappingToApi(values.variable_mapping),
    scheduled_at: values.schedule.mode === 'later' ? values.schedule.at : null,
  }
}
