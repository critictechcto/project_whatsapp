// Single source for brand, contact details and pricing.
// The brand name is a placeholder — change it here.

export const site = {
  name: 'Relaybox',
  domain: 'relaybox.example',
  email: {
    sales: 'sales@relaybox.example',
    support: 'support@relaybox.example',
  },
  trialDays: 14,
  gstRate: 18,
  links: {
    login: '#',
    signup: '#',
    contactSales: 'mailto:sales@relaybox.example',
  },
  nav: [
    { label: 'Product', href: '#product' },
    { label: 'How it works', href: '#how-it-works' },
    { label: 'Pricing', href: '#pricing' },
    { label: 'Developers', href: '#developers' },
    { label: 'FAQ', href: '#faq' },
  ],
} as const

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
