import { Plus, Smartphone } from 'lucide-react'
import { useState } from 'react'
import { Button, EmptyState, PageHeader, Skeleton } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { site } from '../../../config/site'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { AccountCard } from './AccountCard'
import { ConnectWhatsAppDialog } from './ConnectWhatsAppDialog'
import { tierExplanation } from './meta'
import { useWhatsAppAccounts } from './queries'

export function WhatsAppPage() {
  const { can } = useWorkspace()
  const isAdmin = can('admin')
  const accounts = useWhatsAppAccounts()
  const [connectOpen, setConnectOpen] = useState(false)
  const hasAccounts = (accounts.data?.length ?? 0) > 0

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title="WhatsApp"
        description="Numbers connected through Meta's official WhatsApp Business Platform (Cloud API)."
        actions={
          isAdmin &&
          hasAccounts && (
            <Button variant="secondary" icon={<Plus className="size-4" aria-hidden="true" />} onClick={() => setConnectOpen(true)}>
              Connect another number
            </Button>
          )
        }
      />

      {accounts.isPending ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading WhatsApp accounts">
          <Skeleton className="h-28 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
      ) : accounts.isError ? (
        <Notice
          tone="danger"
          role="alert"
          title="Couldn't load your WhatsApp accounts"
          action={
            <Button variant="secondary" size="sm" onClick={() => void accounts.refetch()}>
              Try again
            </Button>
          }
        >
          {actionErrorMessage(accounts.error)}
        </Notice>
      ) : hasAccounts ? (
        accounts.data.map((account) => <AccountCard key={account.id} account={account} />)
      ) : (
        <div className="rounded-xl border border-line bg-card">
          <EmptyState
            icon={<Smartphone className="size-5" aria-hidden="true" />}
            title="Connect your WhatsApp number"
            description={
              isAdmin
                ? "Link a WhatsApp Business Account and phone number with Meta's Embedded Signup. It opens in a Facebook window and usually takes a few minutes."
                : 'No number is connected yet. Ask an admin or the owner of this workspace to connect one.'
            }
            action={
              isAdmin && (
                <Button icon={<Smartphone className="size-4" aria-hidden="true" />} onClick={() => setConnectOpen(true)}>
                  Connect WhatsApp
                </Button>
              )
            }
          />
        </div>
      )}

      <SectionCard id="whatsapp-about" title="About quality and limits">
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="font-medium text-ink">Quality rating</dt>
            <dd className="mt-1 text-[13px] text-muted">
              Meta rates each number from recent customer feedback, such as blocks and reports. A low rating can lead Meta to
              limit how much the number can send.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-ink">Messaging limit</dt>
            <dd className="mt-1 text-[13px] text-muted">{tierExplanation}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink">Templates outside 24 hours</dt>
            <dd className="mt-1 text-[13px] text-muted">
              More than 24 hours after a customer's last message, you can only start a conversation with a template Meta has
              approved.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-ink">Meta pricing</dt>
            <dd className="mt-1 text-[13px] text-muted">
              Under its current pricing, Meta may charge for template messages depending on their category. Those charges are
              separate from your {site.name} plan.
            </dd>
          </div>
        </dl>
      </SectionCard>

      {connectOpen && <ConnectWhatsAppDialog onClose={() => setConnectOpen(false)} />}
    </div>
  )
}
