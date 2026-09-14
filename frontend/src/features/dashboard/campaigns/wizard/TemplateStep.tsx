import { useFormContext, useWatch } from 'react-hook-form'
import { Link } from 'react-router'
import { Field, Input, StatusBadge, TemplatePicker } from '../../../../components/app'
import { useWorkspace } from '../../../../lib/workspace'
import { Notice } from '../components/Notice'
import { normaliseMapping } from '../variables'
import type { WizardValues } from '../wizardSchema'
import { useTemplate } from './queries'

const categoryInfo = {
  MARKETING: {
    label: 'Marketing',
    tone: 'amber',
    text: 'Goes only to contacts with a recorded marketing opt-in. Meta charges marketing rates and may cap how many marketing messages one person receives.',
  },
  UTILITY: { label: 'Utility', tone: 'blue', text: 'For updates about an order, booking or account the customer already has with you.' },
  AUTHENTICATION: { label: 'Authentication', tone: 'blue', text: 'For one-time passcodes. Campaigns are rarely the right way to send these.' },
} as const

export function TemplateStep() {
  const {
    register,
    control,
    setValue,
    formState: { errors },
  } = useFormContext<WizardValues>()
  const { workspaceId } = useWorkspace()
  const templateId = useWatch({ control, name: 'template_id' })
  const template = useTemplate(workspaceId, templateId || undefined)
  const info = template.data ? categoryInfo[template.data.category] : null

  return (
    <div className="flex flex-col gap-5">
      <Field label="Campaign name" hint="Only your team sees this." error={errors.name?.message} required>
        <Input {...register('name')} placeholder="Diwali sale 2026" maxLength={120} autoComplete="off" />
      </Field>

      <Field label="Template" error={errors.template_id?.message} required>
        <TemplatePicker
          value={templateId || null}
          onChange={(selected) => {
            setValue('template_id', selected?.id ?? '', { shouldDirty: true, shouldValidate: Boolean(errors.template_id) })
            if (selected) setValue('variable_mapping', normaliseMapping(selected), { shouldDirty: true })
          }}
          aria-invalid={Boolean(errors.template_id)}
        />
      </Field>

      {info && (
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
          <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
          <span>{info.text}</span>
        </div>
      )}

      <Notice title="Only approved templates are listed">
        WhatsApp only lets businesses start conversations with templates Meta has approved. Templates that are still in review, were
        rejected, or were paused by Meta don't appear here.{' '}
        <Link to={`/app/w/${workspaceId}/templates`} className="text-accent-2 underline underline-offset-4">
          Manage templates
        </Link>
      </Notice>
    </div>
  )
}
