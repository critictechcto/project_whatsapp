import { legalReady, site } from '../../config/site'

function orPending(value: string) {
  return value.trim() ? value : 'Pending'
}

/** Operator, address and effective date from `site.legal`, with a draft note until every field is filled. */
export function LegalDetails() {
  const { legal } = site
  const rows = [
    { label: 'Operated by', value: orPending(legal.entityName) },
    { label: 'Registered address', value: orPending(legal.registeredAddress) },
    { label: 'Effective date', value: orPending(legal.effectiveDate) },
  ]

  return (
    <div className="space-y-4">
      {!legalReady && (
        <p
          role="note"
          className="rounded-md border border-amber/30 bg-amber-soft px-4 py-3 text-[14.5px] leading-relaxed text-amber"
        >
          <strong className="font-semibold">Draft — details pending.</strong> This page is not final yet. The legal
          entity, address, grievance officer and effective date will be added before it takes effect.
        </p>
      )}
      <dl className="grid gap-x-8 gap-y-3 rounded-md border border-line bg-card px-5 py-4 text-[14.5px] sm:grid-cols-[auto_1fr]">
        {rows.map((row) => (
          <div key={row.label} className="contents">
            <dt className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted sm:pt-1">{row.label}</dt>
            <dd className="whitespace-pre-line">{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/** The grievance officer's name and email from `site.legal`. */
export function GrievanceOfficer() {
  const { name, email } = site.legal.grievanceOfficer
  return (
    <p>
      Grievance officer: <strong className="font-semibold">{orPending(name)}</strong>
      {email.trim() ? (
        <>
          ,{' '}
          <a href={`mailto:${email}`} className="text-accent-2 underline underline-offset-[3px]">
            {email}
          </a>
        </>
      ) : (
        ' (contact details pending)'
      )}
      .
    </p>
  )
}
