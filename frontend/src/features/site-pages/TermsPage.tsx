/*
 * LEGAL REVIEW REQUIRED: these terms are a plain-language draft written from how the product works.
 * Have a lawyer review them (limitation of liability, indemnity, governing law and jurisdiction,
 * consumer and IT law, Meta and payment gateway terms) and fill `site.legal` in config/site.ts
 * before publishing them as final.
 */
import { ANNUAL_MONTHS_CHARGED, legalReady, plans, site } from '../../config/site'
import { formatINR } from '../../lib/format'
import { LegalDetails } from './LegalDetails'
import { PageLayout } from './PageLayout'
import { BulletList, ProseSection, TextLink } from './prose'

const META_POLICY_URL = 'https://business.whatsapp.com/policy'

export function TermsPage() {
  const { name, legal } = site
  const supportMail = `mailto:${site.email.support}`
  const courts = legal.jurisdictionCity.trim() ? `the courts at ${legal.jurisdictionCity}, India` : 'the courts of India'
  const freeMonths = 12 - ANNUAL_MONTHS_CHARGED

  return (
    <PageLayout
      title={`Terms of service — ${name}`}
      description={`The terms that apply when a business uses ${name} to message customers and sell on the WhatsApp Business Platform.`}
      eyebrow="Legal"
      heading="Terms of service"
      lead={`These terms are an agreement between ${name} and the business that creates a ${name} account. By creating an account or using the service, you accept them on behalf of that business.`}
      aside={<LegalDetails />}
      noindex={!legalReady}
    >
      <ProseSection id="service" title="The service">
        <p>
          {name} is software that lets a business connect its own WhatsApp number to Meta’s official WhatsApp Business
          Platform (Cloud API), and use it to send campaigns and reminders, reply from a shared inbox, run automations,
          and take orders on WhatsApp. {name} is an independent product and is not affiliated with or endorsed by Meta.
          Your use of WhatsApp is also governed by Meta’s terms and policies.
        </p>
      </ProseSection>

      <ProseSection id="accounts" title="Accounts and workspaces">
        <BulletList>
          <li>You must give accurate details and be authorised to act for the business that owns the workspace.</li>
          <li>
            Keep sign-in details secure. You are responsible for what happens in your workspace, including the actions
            of team members you invite and the roles you give them.
          </li>
          <li>Tell us promptly at {site.email.support} if you think your account has been misused.</li>
        </BulletList>
      </ProseSection>

      <ProseSection id="acceptable-use" title="Acceptable use and WhatsApp rules">
        <p>
          You must follow applicable law and Meta’s{' '}
          <TextLink href={META_POLICY_URL} external>
            WhatsApp Business Messaging Policy and Commerce Policy
          </TextLink>
          . In particular, you agree to:
        </p>
        <BulletList>
          <li>message only people who have given you recorded opt-in to receive WhatsApp messages from you;</li>
          <li>
            use message templates approved by Meta for business-initiated messages outside the 24-hour customer service
            window;
          </li>
          <li>honour STOP and other opt-out requests promptly;</li>
          <li>not send spam, misleading content, or messages about goods and services that Meta’s policies prohibit;</li>
          <li>not use {name} to break the law, infringe others’ rights, or harm the service or other users.</li>
        </BulletList>
        <p>
          Meta sets messaging limits and quality ratings, reviews templates, and may restrict or ban a number or
          business account. {name} does not control those decisions. We may suspend features or accounts that put the
          service, other customers or WhatsApp access at risk.
        </p>
      </ProseSection>

      <ProseSection id="commerce" title="Selling on WhatsApp">
        <BulletList>
          <li>
            You are the seller. You are responsible for your products and their descriptions, prices, stock, delivery,
            returns, refunds, customer service, invoices and taxes.
          </li>
          <li>
            {name} provides software only. We are not a party to transactions between you and your buyers and are not
            responsible for their performance.
          </li>
          <li>
            Buyers pay through your own Razorpay or Cashfree account. {name} does not receive or hold buyers’ money;
            your payment gateway’s terms apply to those payments.
          </li>
          <li>You must handle buyers’ personal data lawfully, including giving them any notices the law requires.</li>
        </BulletList>
      </ProseSection>

      <ProseSection id="plans" title="Trial, plans and payment">
        <p>
          New workspaces get a {site.trialDays}-day free trial. After the trial, continuing to use paid features needs a
          subscription to one of our plans. Current plans are:
        </p>
        <BulletList>
          {plans.map((plan) => (
            <li key={plan.id}>
              <strong className="font-semibold">{plan.name}</strong> — {formatINR(plan.monthlyPrice)} per month billed
              monthly, or {formatINR(plan.monthlyPrice * ANNUAL_MONTHS_CHARGED)} per year billed annually.
            </li>
          ))}
        </BulletList>
        <p>
          Prices are in Indian rupees and exclude GST, which is added at {site.gstRate}% or the rate that applies at the
          time. Annual billing charges {ANNUAL_MONTHS_CHARGED} months for a full year ({freeMonths} months free).
          Subscriptions are billed in advance through Razorpay and renew until cancelled. Plan limits (such as numbers,
          team members and contacts) are shown on the pricing page and in the dashboard. We may change prices or plans
          with notice before your next billing period.
        </p>
        <p>
          <strong className="font-semibold">WhatsApp charges from Meta.</strong> Under Meta’s current pricing, Meta
          charges for certain WhatsApp messages and bills those charges to your own WhatsApp Business Account, not
          through {name}. Meta sets and may change those prices.
        </p>
      </ProseSection>

      <ProseSection id="data" title="Your data">
        <p>
          You own the content and data you bring to {name}. You give us permission to process it only to provide and
          improve the service, as described in our privacy policy. For your contacts’ and buyers’ personal data, you
          are the data fiduciary and we process it on your behalf.
        </p>
      </ProseSection>

      <ProseSection id="availability" title="Availability and changes to the service">
        <p>
          We work to keep {name} available and reliable, but we do not promise it will be uninterrupted or error-free.
          The service depends on third parties, including Meta’s WhatsApp Business Platform, payment gateways and
          hosting providers, whose outages or changes can affect it. We may add, change or remove features over time.
        </p>
      </ProseSection>

      <ProseSection id="liability" title="Disclaimers and limitation of liability">
        <p>
          To the extent the law allows, the service is provided “as is”, and {name} is not liable for indirect or
          consequential losses, lost profits or revenue, lost data, or losses caused by Meta, payment gateways or other
          third parties, including restrictions on your WhatsApp number. To the extent the law allows, our total
          liability for any claim relating to the service is limited to the fees you paid us for the service in the
          three months before the claim arose.
        </p>
        <p>
          You agree to compensate {name} for claims and losses that arise from your messages, your products and
          sales, or your breach of these terms or the law.
        </p>
      </ProseSection>

      <ProseSection id="termination" title="Cancellation, suspension and termination">
        <p>
          You can cancel your subscription at any time; it stays active until the end of the paid period. We may suspend
          or end your access if you seriously or repeatedly break these terms, fail to pay, or if the law or Meta
          requires it. Where reasonable, we will give notice first. After termination you can ask for an export of your
          data for a limited period, after which we delete it as set out in our privacy policy.
        </p>
      </ProseSection>

      <ProseSection id="law" title="Governing law">
        <p>
          These terms are governed by the laws of India. Subject to applicable law, disputes are subject to the
          exclusive jurisdiction of {courts}.
        </p>
      </ProseSection>

      <ProseSection id="changes" title="Changes to these terms">
        <p>
          We may update these terms. We will change the effective date above and, for material changes, notify account
          owners by email or in the dashboard before they take effect. Continuing to use {name} after that means you
          accept the updated terms.
        </p>
      </ProseSection>

      <ProseSection id="contact" title="Contact">
        <p>
          Questions about these terms: <TextLink href={supportMail}>{site.email.support}</TextLink>.
        </p>
      </ProseSection>
    </PageLayout>
  )
}
