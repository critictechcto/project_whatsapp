import { Link } from 'react-router'
import { Button, buttonClasses, Skeleton } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { stateName } from './gst'
import { isProfileComplete, useBillingProfile } from './queries'

export function BillingProfileSummary() {
  const { workspaceId, can } = useWorkspace()
  const isOwner = can('owner')
  const profile = useBillingProfile()
  const complete = isProfileComplete(profile.data)
  const to = `/app/w/${workspaceId}/billing/profile`

  return (
    <SectionCard
      id="billing-profile"
      title="Billing details"
      description="Shown on your GST invoices."
      actions={
        profile.isSuccess &&
        complete && (
          <Link to={to} className={buttonClasses('secondary', 'sm')}>
            {isOwner ? 'Edit' : 'View'}
          </Link>
        )
      }
    >
      {profile.isPending ? (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading billing details">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-4 w-40" />
        </div>
      ) : profile.isError ? (
        <Notice
          tone="danger"
          role="alert"
          title="Couldn't load billing details"
          action={
            <Button variant="secondary" size="sm" onClick={() => void profile.refetch()}>
              Try again
            </Button>
          }
        >
          {actionErrorMessage(profile.error)}
        </Notice>
      ) : complete ? (
        <dl className="grid gap-3 text-sm">
          <div>
            <dt className="text-[12.5px] text-muted">Legal name</dt>
            <dd className="font-medium text-ink">{profile.data.legal_name}</dd>
          </div>
          <div>
            <dt className="text-[12.5px] text-muted">GSTIN</dt>
            <dd className="font-mono text-[13px] text-ink">{profile.data.gstin || <span className="font-sans text-muted">Not GST-registered</span>}</dd>
          </div>
          <div>
            <dt className="text-[12.5px] text-muted">Address</dt>
            <dd className="text-ink">
              {[profile.data.address_line1, profile.data.address_line2, profile.data.city].filter(Boolean).join(', ')}
              <br />
              {stateName(profile.data.state_code) ?? profile.data.state_code} {profile.data.postal_code}
            </dd>
          </div>
          <div>
            <dt className="text-[12.5px] text-muted">Invoice email</dt>
            <dd className="text-ink">{profile.data.email}</dd>
          </div>
        </dl>
      ) : (
        <div className="flex flex-col items-start gap-3 text-sm">
          <p className="text-muted">
            No billing details yet. Add your business name and address, and your GSTIN if you're GST-registered, before
            subscribing.
          </p>
          {isOwner ? (
            <Link to={to} className={buttonClasses('secondary', 'sm')}>
              Add billing details
            </Link>
          ) : (
            <p className="text-[13px] text-muted">Only the workspace owner can add them.</p>
          )}
        </div>
      )}
    </SectionCard>
  )
}
