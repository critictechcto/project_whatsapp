/*
 * LEGAL REVIEW REQUIRED: this privacy policy is a plain-language draft written from how the product
 * works. Have a lawyer review it (DPDP Act 2023, IT Act 2000 and IT Rules, Meta and payment gateway
 * terms) and fill `site.legal` in config/site.ts before publishing it as final.
 */
import { legalReady, site } from '../../config/site'
import { GrievanceOfficer, LegalDetails } from './LegalDetails'
import { PageLayout } from './PageLayout'
import { BulletList, ProseSection, Subheading, TextLink } from './prose'

export function PrivacyPage() {
  const { name } = site
  const supportMail = `mailto:${site.email.support}`

  return (
    <PageLayout
      title={`Privacy policy — ${name}`}
      description={`How ${name} collects, uses and protects personal data when businesses use it to message customers on the WhatsApp Business Platform.`}
      eyebrow="Legal"
      heading="Privacy policy"
      lead={`This policy explains what personal data ${name} processes, why, who we share it with and the choices you have. We have tried to keep it in plain language.`}
      aside={<LegalDetails />}
      noindex={!legalReady}
    >
      <ProseSection id="who-we-are" title="Who this policy covers">
        <p>
          {name} is a software service that lets businesses in India send and receive WhatsApp messages through
          Meta’s official WhatsApp Business Platform (Cloud API), and sell to their customers on WhatsApp. It is
          operated by the entity named above (“{name}”, “we”, “us”).
        </p>
        <p>This policy covers two groups of people:</p>
        <BulletList>
          <li>
            <strong className="font-semibold">Our customers and their team members</strong> — businesses that sign up
            for {name} (“sellers” or “businesses”) and the people they invite to their workspace.
          </li>
          <li>
            <strong className="font-semibold">People who message those businesses</strong> — their contacts and
            buyers on WhatsApp.
          </li>
        </BulletList>
      </ProseSection>

      <ProseSection id="roles" title="Our role for each kind of data">
        <p>
          For account and billing data about our customers, we decide how the data is used, so we act as the data
          fiduciary (controller).
        </p>
        <p>
          For the messages, contacts, orders and addresses a business handles through {name}, the business decides why
          and how that data is processed. The business is the data fiduciary (controller) for its contacts and buyers,
          and {name} processes that data on the business’s behalf as a data processor. If you are a contact or buyer
          of a business that uses {name}, please contact that business first about your data; we will help them
          respond.
        </p>
      </ProseSection>

      <ProseSection id="data-we-process" title="What we process">
        <Subheading>Account and workspace data</Subheading>
        <BulletList>
          <li>Your name, email address and password (stored only as a secure hash).</li>
          <li>Workspace details such as business name, team members, their roles and invitations.</li>
          <li>Activity needed to run and secure the service, such as sign-in times, IP address and device details.</li>
        </BulletList>

        <Subheading>WhatsApp business data</Subheading>
        <p>
          When a business connects its number through Meta’s Embedded Signup, we process data exchanged with Meta’s
          WhatsApp Business Platform (Cloud API) on its behalf:
        </p>
        <BulletList>
          <li>Messages sent and received, their delivery and read status, and media files such as images or documents.</li>
          <li>Contacts: names, WhatsApp phone numbers, tags, opt-in and opt-out records.</li>
          <li>Message templates, campaigns and automation settings.</li>
          <li>
            Access tokens and identifiers issued by Meta for the business’s WhatsApp account. We store tokens
            encrypted and use them only to operate the features the business has turned on.
          </li>
        </BulletList>

        <Subheading>Orders and buyer data</Subheading>
        <p>
          When a business sells on WhatsApp through {name}, we process buyer names, phone numbers, delivery addresses,
          carts, orders and payment status for that business, as its processor.
        </p>

        <Subheading>Payments</Subheading>
        <BulletList>
          <li>
            Buyers pay a business through that business’s own Razorpay or Cashfree account. {name} creates payment links
            and receives the payment status, but does not receive or hold buyers’ money and does not see full card or
            bank details.
          </li>
          <li>
            Our own subscription fees are billed through Razorpay. We receive billing details and payment status from
            Razorpay, not full card or bank details.
          </li>
        </BulletList>
      </ProseSection>

      <ProseSection id="how-we-use" title="How we use data">
        <BulletList>
          <li>To provide the service: sending and receiving messages, running campaigns, automations and shops.</li>
          <li>To create and secure accounts, prevent abuse and investigate problems.</li>
          <li>To bill subscriptions and keep the records that tax and accounting law requires.</li>
          <li>To send service emails, such as invitations, password resets, billing notices and important changes.</li>
          <li>To help businesses follow WhatsApp rules, for example by recording opt-ins and honouring opt-outs.</li>
        </BulletList>
        <p>
          We do not sell personal data, and we do not use a business’s messages, contacts or buyer data for our own
          advertising.
        </p>
      </ProseSection>

      <ProseSection id="sharing" title="Who we share data with">
        <p>We share data only with service providers that help us run {name}, and only as needed:</p>
        <BulletList>
          <li>
            <strong className="font-semibold">DigitalOcean</strong> — hosting, databases and file storage, in its India
            region.
          </li>
          <li>
            <strong className="font-semibold">Meta Platforms</strong> — to send and receive WhatsApp messages through
            the WhatsApp Business Platform. Meta’s own terms and privacy policy apply to data on WhatsApp.
          </li>
          <li>
            <strong className="font-semibold">Razorpay</strong> — subscription billing, and payment links when a
            business connects its own Razorpay account. <strong className="font-semibold">Cashfree</strong> — payment
            links when a business connects its own Cashfree account.
          </li>
          <li>
            <strong className="font-semibold">An email delivery provider</strong> — to send service emails.
          </li>
        </BulletList>
        <p>
          We may also disclose data when the law requires it, for example to comply with a valid order from a court or
          government authority, or to protect the rights and safety of our users and the public.
        </p>
      </ProseSection>

      <ProseSection id="cookies" title="Cookies and local storage">
        <p>
          The marketing site does not use advertising or tracking cookies. When you sign in to the dashboard, we keep a
          sign-in refresh token in your browser’s local storage so you stay signed in; signing out removes it. The
          short-lived access token stays in memory only.
        </p>
      </ProseSection>

      <ProseSection id="security" title="How we protect data">
        <p>
          We use encryption in transit (HTTPS), encrypt Meta access tokens and other secrets at rest, limit access by
          workspace and role, and keep each business’s data separate from other businesses. No system is perfectly
          secure, but we work to protect data and will notify affected businesses and authorities of a personal data
          breach as the law requires.
        </p>
      </ProseSection>

      <ProseSection id="retention" title="Retention and deletion">
        <p>
          We keep data for as long as a workspace is active and as needed to provide the service. When a business
          deletes data or closes its workspace, we delete or anonymise that data within a reasonable period, except
          where we must keep records longer for legal, tax or dispute reasons. Copies in backups are removed as those
          backups expire.
        </p>
      </ProseSection>

      <ProseSection id="your-rights" title="Your rights">
        <p>
          Under India’s Digital Personal Data Protection Act, 2023 and applicable rules, you may have the right to:
        </p>
        <BulletList>
          <li>access information about the personal data we process about you;</li>
          <li>correct, complete, update or erase your personal data;</li>
          <li>withdraw consent where processing is based on consent;</li>
          <li>nominate someone to exercise your rights if you are unable to; and</li>
          <li>have your grievances addressed.</li>
        </BulletList>
        <p>
          To use these rights for your {name} account, write to{' '}
          <TextLink href={supportMail}>{site.email.support}</TextLink>. If your data came to us from a business you
          interacted with on WhatsApp, contact that business; we will support it in responding. To stop receiving
          messages from a business, you can reply STOP or block the number in WhatsApp.
        </p>
      </ProseSection>

      <ProseSection id="grievances" title="Grievance officer">
        <p>
          In line with the Information Technology Act, 2000, the rules made under it and the Digital Personal Data
          Protection Act, 2023, you can raise a complaint about how we handle personal data with our grievance officer:
        </p>
        <GrievanceOfficer />
        <p>
          We aim to acknowledge complaints promptly and resolve them within the time the law allows. If you are not
          satisfied with our response, you may be able to complain to the Data Protection Board of India.
        </p>
      </ProseSection>

      <ProseSection id="children" title="Children">
        <p>
          {name} is a business tool and is not meant for children. We do not knowingly create accounts for anyone under
          18.
        </p>
      </ProseSection>

      <ProseSection id="changes" title="Changes to this policy">
        <p>
          We may update this policy as the product or the law changes. We will change the effective date above and, for
          material changes, notify account owners by email or in the dashboard before the change takes effect.
        </p>
      </ProseSection>

      <ProseSection id="contact" title="Contact">
        <p>
          Questions about this policy: <TextLink href={supportMail}>{site.email.support}</TextLink>.
        </p>
      </ProseSection>
    </PageLayout>
  )
}
