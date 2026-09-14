import { useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'
import { Combobox, Field, Skeleton, statusInfo } from '../../../../components/app'
import { formatNumber } from '../../../../lib/format'
import { useWorkspace } from '../../../../lib/workspace'
import { campaignError } from '../campaignErrors'
import { Notice } from '../components/Notice'
import { RadioCards } from '../components/RadioCards'
import { useAudiencePreview, useDebouncedJson } from '../useAudiencePreview'
import type { WizardValues } from '../wizardSchema'
import { useContactOptions, useTagOptions, useTemplate } from './queries'

export function AudienceStep({ campaignId }: { campaignId: string | undefined }) {
  const {
    control,
    setValue,
    formState: { errors },
  } = useFormContext<WizardValues>()
  const { workspaceId } = useWorkspace()
  const audience = useWatch({ control, name: 'audience' })
  const templateId = useWatch({ control, name: 'template_id' })
  const template = useTemplate(workspaceId, templateId || undefined)
  const tags = useTagOptions(workspaceId)
  const [search, setSearch] = useState('')
  const contacts = useContactOptions(workspaceId, useDebouncedJson(search, 250))
  const [contactLabels, setContactLabels] = useState<Record<string, string>>({})
  const preview = useAudiencePreview(workspaceId, campaignId, audience)

  const audienceError = errors.audience?.message ?? errors.audience?.tag_ids?.message
  const update = (patch: Partial<WizardValues['audience']>) =>
    setValue('audience', { ...audience, ...patch }, { shouldDirty: true, shouldValidate: Boolean(audienceError) })

  const tagOptions = (tags.data ?? []).map((tag) => ({ value: tag.id, label: tag.name }))
  const contactOptions = (contacts.data ?? []).map((contact) => ({
    value: contact.id,
    label: contact.name || contact.phone_e164,
    description: `${contact.phone_e164} · Marketing: ${statusInfo(contact.marketing_opt_in_status).label.toLowerCase()}`,
  }))
  const marketing = template.data?.category === 'MARKETING'
  const stats = preview.data

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="flex flex-col gap-5">
        <Field label="Tags" hint="Contacts with these tags receive the campaign." error={audienceError}>
          <Combobox
            multiple
            options={tagOptions}
            value={audience.tag_ids}
            onChange={(tagIds) => update({ tag_ids: tagIds })}
            loading={tags.isPending}
            placeholder="Choose tags"
            emptyText="No tags found"
            aria-invalid={Boolean(audienceError)}
          />
        </Field>

        <RadioCards
          legend="Match"
          value={audience.match}
          onChange={(match) => update({ match })}
          disabled={audience.tag_ids.length < 2}
          options={[
            { value: 'any', label: 'Any of these tags', description: 'Contacts with at least one of the tags.' },
            { value: 'all', label: 'All of these tags', description: 'Only contacts that have every tag.' },
          ]}
        />

        <Field label="Individual contacts" hint="Optional. Added on top of the tag audience.">
          <Combobox
            multiple
            options={contactOptions}
            value={audience.contact_ids}
            onChange={(contactIds) => {
              const labels = Object.fromEntries(contactOptions.filter((option) => contactIds.includes(option.value)).map((option) => [option.value, option.label]))
              setContactLabels((previous) => ({ ...previous, ...labels }))
              update({ contact_ids: contactIds })
            }}
            onSearchChange={setSearch}
            filter={false}
            loading={contacts.isFetching}
            selectedLabels={contactLabels}
            placeholder="Search by name or phone"
            emptyText="No contacts found"
          />
        </Field>

        <Notice title={marketing ? 'Marketing templates need opt-in' : 'Opt-outs are always respected'}>
          {marketing
            ? 'People should only get marketing messages on WhatsApp after agreeing to them. Contacts without a recorded marketing opt-in are skipped, and so is anyone who opted out, for example by replying STOP.'
            : "Contacts who opted out are skipped. Utility templates don't need a marketing opt-in, but people should still expect to hear from you."}
        </Notice>
      </div>

      <section aria-labelledby="audience-preview-heading" aria-live="polite" className="h-fit rounded-xl border border-line bg-paper-2/50 p-4">
        <div className="flex items-baseline justify-between gap-2">
          <h3 id="audience-preview-heading" className="font-display text-base font-semibold text-ink">
            Who receives it
          </h3>
          {preview.isFetching && <span className="text-[12px] text-muted">Updating…</span>}
        </div>

        {preview.empty ? (
          <p className="mt-2 text-sm text-muted">Choose at least one tag or contact to see who's included.</p>
        ) : preview.isError ? (
          <Notice tone="error" className="mt-3">
            {campaignError(preview.error).message}
          </Notice>
        ) : !stats ? (
          <div className="mt-3 flex flex-col gap-2">
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-4 w-full" />
          </div>
        ) : (
          <>
            <dl className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <dt className="text-[12px] text-muted">In audience</dt>
                <dd className="font-display text-2xl font-semibold tabular-nums text-ink">{formatNumber(stats.total)}</dd>
              </div>
              <div>
                <dt className="text-[12px] text-muted">Will receive it</dt>
                <dd className="font-display text-2xl font-semibold tabular-nums text-accent-2">{formatNumber(stats.eligible)}</dd>
              </div>
            </dl>
            <dl className="mt-3 flex flex-col gap-1.5 border-t border-line-2 pt-3 text-[13px]">
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Skipped: opted out</dt>
                <dd className="font-mono text-ink">{formatNumber(stats.skipped.opted_out)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Skipped: no marketing opt-in</dt>
                <dd className="font-mono text-ink">{formatNumber(stats.skipped.not_opted_in)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Skipped: invalid number</dt>
                <dd className="font-mono text-ink">{formatNumber(stats.skipped.invalid)}</dd>
              </div>
            </dl>
            <p className="mt-3 text-[12px] text-muted">The final list is fixed when the campaign starts, so these numbers can still change.</p>
          </>
        )}
      </section>
    </div>
  )
}
