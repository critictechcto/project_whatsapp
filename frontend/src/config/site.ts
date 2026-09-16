// Single source for brand, contact details and pricing.
// Brand: UpChatz (upchatz.com).

const BASE_URL = import.meta.env.BASE_URL

/**
 * Legal details shown on the privacy policy and terms of service pages. The owner must fill every
 * field before launch: until then `legalReady` is false, the footer hides the legal links, and the
 * pages show a visible draft note and are marked `noindex`.
 */
export type LegalDetails = {
  /** Registered legal name of the business that operates UpChatz. */
  entityName: string
  registeredAddress: string
  /** Grievance officer under the Digital Personal Data Protection Act, 2023 and the IT Rules. */
  grievanceOfficer: { name: string; email: string }
  /** Date the current policy text takes effect, as displayed, e.g. "1 October 2026". */
  effectiveDate: string
  /** City whose courts have jurisdiction under the terms, e.g. "Bengaluru". */
  jurisdictionCity: string
}

const legal: LegalDetails = {
  entityName: '',
  registeredAddress: '',
  grievanceOfficer: { name: '', email: '' },
  effectiveDate: '',
  jurisdictionCity: '',
}

export const site = {
  name: 'UpChatz',
  domain: 'upchatz.com',
  email: {
    sales: 'sales@upchatz.com',
    support: 'support@upchatz.com',
  },
  trialDays: 14,
  gstRate: 18,
  links: {
    // Dashboard routes, prefixed with the deploy base (`/` or the GitHub Pages project path).
    login: `${BASE_URL}app/login`,
    signup: `${BASE_URL}app/register`,
    contactSales: 'mailto:sales@upchatz.com',
    // Static pages. GitHub Pages serves them from `<page>/index.html` (see deploy-pages.yml).
    privacy: `${BASE_URL}privacy/`,
    terms: `${BASE_URL}terms/`,
    contact: `${BASE_URL}contact/`,
  },
  legal,
  /** Landing page sections linked from the navbar; build hrefs with `sectionHref(id)`. */
  nav: [
    { label: 'Product', id: 'product' },
    { label: 'Sell on WhatsApp', id: 'sell' },
    { label: 'How it works', id: 'how-it-works' },
    { label: 'Pricing', id: 'pricing' },
    { label: 'Developers', id: 'developers' },
    { label: 'FAQ', id: 'faq' },
  ],
} as const

/** True only when every `site.legal` field is filled in. */
export const legalReady = [
  legal.entityName,
  legal.registeredAddress,
  legal.grievanceOfficer.name,
  legal.grievanceOfficer.email,
  legal.effectiveDate,
  legal.jurisdictionCity,
].every((value) => value.trim().length > 0)

/** True when `pathname` is the landing page (the deploy base root). */
export function isLandingPath(pathname: string = window.location.pathname) {
  return pathname === BASE_URL || pathname === BASE_URL.replace(/\/$/, '') || pathname === `${BASE_URL}index.html`
}

/** Link to a landing page section that works both on the landing page and on the other pages. */
export function sectionHref(id: string, pathname: string = window.location.pathname) {
  return isLandingPath(pathname) ? `#${id}` : `${BASE_URL}#${id}`
}

export type Plan = {
  id: string
  name: string
  monthlyPrice: number
  blurb: string
  limits: string[]
  features: string[]
  recommended?: boolean
}

/** Annual billing charges this many months for a full year. */
export const ANNUAL_MONTHS_CHARGED = 10

export const plans: Plan[] = [
  {
    id: 'starter',
    name: 'Starter',
    monthlyPrice: 999,
    blurb: 'For small shops and clinics starting with WhatsApp.',
    limits: ['1 WhatsApp number', '2 team members', '5,000 contacts'],
    features: [
      'Bulk campaigns',
      'Template manager',
      'Shared team inbox',
      'Basic auto-replies',
      'Opt-in & opt-out tracking',
      'Email support',
    ],
  },
  {
    id: 'growth',
    name: 'Growth',
    monthlyPrice: 2499,
    blurb: 'For growing brands sending every day.',
    limits: ['2 WhatsApp numbers', '5 team members', '25,000 contacts'],
    features: [
      'Everything in Starter',
      'Scheduled & recurring campaigns',
      'Keyword automations',
      'Delivery, read & reply analytics',
      'REST API & webhooks',
      'Chat & email support',
    ],
    recommended: true,
  },
  {
    id: 'pro',
    name: 'Pro',
    monthlyPrice: 5999,
    blurb: 'For teams running WhatsApp as a core channel.',
    limits: ['5 WhatsApp numbers', '15 team members', '1,00,000 contacts'],
    features: [
      'Everything in Growth',
      'Advanced automation flows',
      'Custom roles & per-number access',
      'Audit log',
      'Onboarding call & verification help',
      'Priority phone support',
    ],
  },
]
