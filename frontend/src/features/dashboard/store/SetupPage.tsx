import { Circle, CircleCheck, ExternalLink } from 'lucide-react'
import { Link } from 'react-router'
import { errorMessage } from '../../../api/errors'
import { Button, buttonClasses, Input, Skeleton } from '../../../components/app'
import { cn } from '../../../lib/cn'
import { useWorkspace } from '../../../lib/workspace'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { useStoreChecklist, useStoreSettings, type StoreChecklistItem } from './api'
import { CopyButton } from './components/CopyButton'
import { StoreFrame } from './components/StoreNav'

export const WHATSAPP_MANAGER_URL = 'https://business.facebook.com/wa/manage/home/'

/** Title and the screen that fixes each checklist item, relative to the workspace. */
const checklistSteps: Record<string, { title: string; to: string; action: string }> = {
  whatsapp_connected: { title: 'Connect your WhatsApp number', to: 'whatsapp', action: 'Connect WhatsApp' },
  products_added: { title: 'Add products', to: 'catalog', action: 'Add products' },
  payments_configured: { title: 'Choose how buyers pay', to: 'store/payments', action: 'Set up payments' },
  order_templates_ready: { title: 'Pick order update templates', to: 'store/notifications', action: 'Choose templates' },
  alert_number_verified: { title: 'Get new-order alerts on WhatsApp', to: 'store/alerts', action: 'Add alert number' },
  store_enabled: { title: 'Turn on the store', to: 'store/settings', action: 'Open store settings' },
}

function ChecklistRow({ item }: { item: StoreChecklistItem }) {
  const { workspaceId } = useWorkspace()
  const step = checklistSteps[item.key] ?? { title: item.key.replace(/_/g, ' '), to: 'store', action: 'Open' }
  return (
    <li className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        {item.done ? (
          <CircleCheck className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden="true" />
        ) : (
          <Circle className="mt-0.5 size-5 shrink-0 text-line" aria-hidden="true" />
        )}
        <div className="min-w-0">
          <p className={cn('font-medium', item.done ? 'text-muted' : 'text-ink')}>
            {step.title}
            <span className="sr-only">{item.done ? ' (done)' : ' (to do)'}</span>
          </p>
          {item.detail && <p className="text-[13px] text-muted">{item.detail}</p>}
        </div>
      </div>
      <Link
        to={`/app/w/${workspaceId}/${step.to}`}
        className={cn(buttonClasses(item.done ? 'ghost' : 'secondary', 'sm'), 'self-start sm:self-center')}
      >
        {step.action}
      </Link>
    </li>
  )
}

export function SetupPage() {
  const { workspaceId } = useWorkspace()
  const checklist = useStoreChecklist(workspaceId)
  const settings = useStoreSettings(workspaceId)
  const items = checklist.data?.items ?? []
  const done = items.filter((item) => item.done).length
  const storeLink = settings.data?.store_link

  return (
    <StoreFrame description="Sell on your WhatsApp number: buyers browse, order and pay in the chat, and you get an alert for every order.">
      <SectionCard
        id="store-checklist"
        title="Setup checklist"
        description={checklist.data ? `${done} of ${items.length} steps done` : 'Everything your store needs before buyers can order.'}
      >
        {checklist.isPending ? (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : checklist.isError ? (
          <Notice
            tone="danger"
            role="alert"
            title="Couldn't load the checklist"
            action={
              <Button variant="secondary" size="sm" onClick={() => void checklist.refetch()}>
                Try again
              </Button>
            }
          >
            {errorMessage(checklist.error)}
          </Notice>
        ) : (
          <ol aria-label="Store setup steps" className="-mx-5 -my-4 divide-y divide-line-2">
            {items.map((item) => (
              <ChecklistRow key={item.key} item={item} />
            ))}
          </ol>
        )}
      </SectionCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard id="store-link" title="Share your store" description="Buyers tap the link, WhatsApp opens with “Hi” typed, and your store menu replies.">
          {settings.isPending ? (
            <Skeleton className="h-10" />
          ) : storeLink ? (
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <Input readOnly value={storeLink} aria-label="Store link" className="font-mono text-[13px]" onFocus={(event) => event.target.select()} />
                <div className="flex shrink-0 gap-2">
                  <CopyButton value={storeLink} label="Copy link" aria-label="Copy store link" />
                  <a href={storeLink} target="_blank" rel="noreferrer" className={buttonClasses('secondary', 'sm')}>
                    <ExternalLink className="size-4" aria-hidden="true" />
                    Open in WhatsApp
                  </a>
                </div>
              </div>
              <div className="text-[13px] text-muted">
                <p className="font-medium text-ink">How to share it</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5">
                  <li>Add it to your Instagram bio and Google Business Profile.</li>
                  <li>Send it to regular customers and post it in your WhatsApp Status.</li>
                  <li>Print it on bills, visiting cards and packaging.</li>
                </ul>
                {!settings.data?.enabled && (
                  <p className="mt-2">Until the store is turned on, messages from this link arrive in your inbox like any other chat.</p>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted">
              Your store link appears once a WhatsApp number is connected.{' '}
              <Link to={`/app/w/${workspaceId}/whatsapp`} className="text-accent-2 underline underline-offset-4">
                Connect WhatsApp
              </Link>
            </p>
          )}
        </SectionCard>

        <SectionCard id="message-charges" title="WhatsApp message charges">
          <div className="flex flex-col gap-3 text-sm text-muted">
            <p>
              Under Meta's current pricing, WhatsApp message charges are billed by Meta directly to your WhatsApp Business Account, not by
              UpChatz. Add a payment method in WhatsApp Manager so your messages keep going out.
            </p>
            <p>
              Most shop replies are sent inside the buyer's 24-hour window, which Meta doesn't charge for under its current pricing. Order
              updates sent as templates outside that window may be charged.
            </p>
            <a href={WHATSAPP_MANAGER_URL} target="_blank" rel="noreferrer" className={cn(buttonClasses('secondary', 'sm'), 'self-start')}>
              <ExternalLink className="size-4" aria-hidden="true" />
              Open WhatsApp Manager
            </a>
          </div>
        </SectionCard>
      </div>
    </StoreFrame>
  )
}
