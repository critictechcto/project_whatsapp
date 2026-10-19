import type { ReactNode } from 'react'
import { ArrowUpRight, Building2, LifeBuoy, MessagesSquare } from 'lucide-react'
import { legalReady, sectionHref, site, telHref, whatsappHref } from '../../config/site'
import { PageLayout } from './PageLayout'
import { BulletList, ProseSection, TextLink } from './prose'

const META_STATUS_URL = 'https://metastatus.com/whatsapp-business-api'

const cardClass = 'flex flex-col rounded-lg border border-line bg-card p-6 shadow-[inset_0_1px_0_rgb(255_255_255/0.9)]'
const cardIconClass = 'grid size-10 place-items-center rounded-md bg-accent-soft text-accent-2'
const cardTitleClass = 'mt-5 font-display text-[1.35rem] font-semibold tracking-[-0.02em]'
const companyLinkClass =
  'inline-flex min-h-11 items-center font-mono text-[14px] text-accent-2 underline decoration-accent/40 underline-offset-[3px] hover:decoration-accent-2'

function ContactCard({
  id,
  icon,
  title,
  email,
  children,
}: {
  id: string
  icon: ReactNode
  title: string
  email: string
  children: ReactNode
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={cardClass}>
      <span className={cardIconClass} aria-hidden="true">
        {icon}
      </span>
      <h2 id={`${id}-title`} className={cardTitleClass}>
        {title}
      </h2>
      <div className="mt-2 flex-1 text-[15px] leading-relaxed text-muted">{children}</div>
      <a
        href={`mailto:${email}`}
        className="mt-6 inline-flex items-center gap-1.5 self-start font-mono text-[14px] text-accent-2 underline decoration-accent/40 underline-offset-[3px] hover:decoration-accent-2"
      >
        {email}
      </a>
    </section>
  )
}

/** The operating company from `site.legal`; phone and GSTIN appear only once they are set. */
function CompanyCard() {
  const { entityName, registeredAddress, phone, gstin } = site.legal

  return (
    <section id="company" aria-labelledby="company-title" className={`${cardClass} sm:col-span-2`}>
      <span className={cardIconClass} aria-hidden="true">
        <Building2 className="size-5" />
      </span>
      <h2 id="company-title" className={cardTitleClass}>
        Company
      </h2>
      <address className="mt-2 text-[15px] not-italic leading-relaxed text-muted">
        <p>
          {site.name} is operated by <strong className="font-semibold text-ink">{entityName}</strong>
        </p>
        <p className="mt-1">Registered address: {registeredAddress}</p>
        {gstin && <p className="mt-1">GSTIN: {gstin}</p>}
        {phone && (
          <p className="mt-4 flex flex-wrap gap-x-6">
            <a href={telHref(phone)} className={companyLinkClass}>
              {phone}
            </a>
            <a href={whatsappHref(phone)} target="_blank" rel="noopener noreferrer" className={companyLinkClass}>
              Chat on WhatsApp
            </a>
          </p>
        )}
      </address>
    </section>
  )
}

export function ContactPage() {
  const { name } = site

  return (
    <PageLayout
      title={`Contact — ${name}`}
      description={`Talk to ${name} sales about plans and setup, or email support about your workspace.`}
      eyebrow="Contact"
      heading="Talk to us"
      canonicalPath="contact/"
      lead={`Questions about plans, getting your number connected, or something not working in ${name}? Email the right team and a person will reply.`}
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <ContactCard
          id="sales"
          icon={<MessagesSquare className="size-5" />}
          title="Sales"
          email={site.email.sales}
        >
          Plans and pricing, larger contact volumes, moving from another provider, or help deciding whether {name} fits
          your business.
        </ContactCard>
        <ContactCard id="support" icon={<LifeBuoy className="size-5" />} title="Support" email={site.email.support}>
          Help with an existing workspace: connecting a number, templates, campaigns, the inbox, your shop or billing.
        </ContactCard>
        {legalReady && <CompanyCard />}
      </div>

      <div className="mt-14">
        <ProseSection id="support-request" title="What to include in a support request">
          <p>These details help us find the problem quickly:</p>
          <BulletList>
            <li>your workspace name and the email you sign in with;</li>
            <li>the WhatsApp phone number involved, with country code;</li>
            <li>for a message problem, the message ID if you have it, or the recipient and the approximate date and time;</li>
            <li>what you expected to happen and what happened instead, with any error text; and</li>
            <li>a screenshot, if you can take one.</li>
          </BulletList>
          <p>
            Please don’t send passwords, one-time codes, access tokens or full card details by email. We will never ask
            for them.
          </p>
        </ProseSection>

        <ProseSection id="response" title="When to expect a reply">
          <p>
            We aim to reply within one business day (Monday to Friday, Indian working hours). Response times can vary with your plan (see{' '}
            <TextLink href={sectionHref('pricing')}>pricing</TextLink>) and with volume on busy days.
          </p>
        </ProseSection>

        <ProseSection id="meta-status" title="Messages not sending?">
          <p>
            {name} sends through Meta’s WhatsApp Business Platform. If many messages are failing at once, Meta may be
            having an incident; check{' '}
            <TextLink href={META_STATUS_URL} external>
              Meta’s WhatsApp Business Platform status
              <ArrowUpRight className="ml-0.5 inline size-3.5 align-[-1px]" aria-hidden="true" />
            </TextLink>{' '}
            before writing to us.
          </p>
        </ProseSection>
      </div>
    </PageLayout>
  )
}
