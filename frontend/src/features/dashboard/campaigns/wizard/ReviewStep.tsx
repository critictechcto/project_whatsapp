import type { ReactNode } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'
import { Checkbox, Skeleton, templateVariables } from '../../../../components/app'
import { formatDateTime, timeZoneName } from '../../../../lib/datetime'
import { formatNumber } from '../../../../lib/format'
import { useWorkspace } from '../../../../lib/workspace'
import { useCampaign } from '../api'
import { formatMoney } from '../clock'
import { useAudiencePreview } from '../useAudiencePreview'
import { describeSource } from '../variables'
import type { WizardValues } from '../wizardSchema'
import { useTagOptions, useTemplate } from './queries'

const categoryLabels = { MARKETING: 'Marketing', UTILITY: 'Utility', AUTHENTICATION: 'Authentication' } as const

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[160px_minmax(0,1fr)] sm:gap-4">
      <dt className="text-[13px] text-muted">{label}</dt>
      <dd className="text-sm text-ink">{children}</dd>
    </div>
  )
}

export function ReviewStep({ campaignId }: { campaignId: string | undefined }) {
  const {
    control,
    register,
    formState: { errors },
  } = useFormContext<WizardValues>()
  const { workspaceId, timeZone } = useWorkspace()
  const [name, templateId, audience, mapping, schedule] = useWatch({
    control,
    name: ['name', 'template_id', 'audience', 'variable_mapping', 'schedule'],
  })
  const template = useTemplate(workspaceId, templateId || undefined)
  const tags = useTagOptions(workspaceId)
  const preview = useAudiencePreview(workspaceId, campaignId, audience)
  const campaign = useCampaign(workspaceId, campaignId)

  const tagNames = audience.tag_ids.map((id) => tags.data?.find((tag) => tag.id === id)?.name ?? 'Unknown tag')
  const joiner = audience.match === 'all' ? ' and ' : ' or '
  const spec = template.data ? templateVariables(template.data) : null
  const variables = [
    ...(mapping.header && spec?.header.names.length ? [{ label: `Header {{${spec.header.names[0]}}}`, source: mapping.header }] : []),
    ...mapping.body.map((source, index) => ({ label: `Body {{${spec?.body.names[index] ?? index + 1}}}`, source })),
    ...mapping.buttons.map((entry, index) => ({ label: `Button ${spec?.buttons[index]?.text ?? Number(entry.index) + 1}`, source: entry.source })),
  ]
  const estimate = campaign.data?.estimated_cost

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <dl className="divide-y divide-line-2 border-y border-line-2">
        <Row label="Name">{name}</Row>
        <Row label="Template">
          <span className="font-mono text-[13px]">{template.data?.name ?? '…'}</span>
          {template.data && <span className="text-muted"> · {categoryLabels[template.data.category]}</span>}
        </Row>
        {campaign.data && <Row label="From">{campaign.data.phone_number.display_phone_number}</Row>}
        <Row label="Audience">
          <span className="block">
            {tagNames.length > 0 && <>Tagged {tagNames.map((tag) => `“${tag}”`).join(joiner)}</>}
            {tagNames.length > 0 && audience.contact_ids.length > 0 && ', plus '}
            {audience.contact_ids.length > 0 && `${formatNumber(audience.contact_ids.length)} chosen contact${audience.contact_ids.length === 1 ? '' : 's'}`}
          </span>
          {preview.data ? (
            <span className="mt-0.5 block text-muted">
              {formatNumber(preview.data.eligible)} of {formatNumber(preview.data.total)} will receive it;{' '}
              {formatNumber(preview.data.total - preview.data.eligible)} skipped for consent or invalid numbers.
            </span>
          ) : (
            <Skeleton className="mt-1 h-4 w-48" />
          )}
        </Row>
        <Row label="Variables">
          {variables.length === 0 ? (
            'None'
          ) : (
            <ul className="flex flex-col gap-0.5">
              {variables.map((variable) => (
                <li key={variable.label}>
                  <span className="font-mono text-[12px] text-muted">{variable.label}</span> {describeSource(variable.source)}
                </li>
              ))}
            </ul>
          )}
        </Row>
        <Row label="When">
          {schedule.mode === 'later' && schedule.at
            ? `${formatDateTime(schedule.at, timeZone)} (${timeZoneName(timeZone)})`
            : 'As soon as you launch'}
        </Row>
        <Row label="Estimated cost">
          {estimate ? (
            <>
              <span className="font-mono">{formatMoney(estimate.amount, estimate.currency)}</span>
              <span className="mt-0.5 block text-[13px] text-muted">{estimate.note}</span>
            </>
          ) : (
            <span className="text-muted">Not available yet.</span>
          )}
        </Row>
      </dl>

      <div className="rounded-xl border border-line bg-paper-2/50 p-4">
        <Checkbox
          {...register('consent')}
          label="I confirm these contacts agreed to receive WhatsApp messages from us"
          description="Meta requires opt-in before a business messages people on WhatsApp. Messages people didn't ask for get blocked and reported, which can lower your number's quality rating and messaging limit."
          aria-invalid={Boolean(errors.consent)}
        />
        {errors.consent && (
          <p id="consent-error" role="alert" className="mt-2 text-[13px] text-signal">
            {errors.consent.message}
          </p>
        )}
      </div>
    </div>
  )
}
