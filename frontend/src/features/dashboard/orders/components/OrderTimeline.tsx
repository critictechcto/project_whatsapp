import { Link } from 'react-router'
import { errorMessage } from '../../../../api/errors'
import { Button, Skeleton } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { formatDateTime } from '../../../../lib/datetime'
import { useWorkspace } from '../../../../lib/workspace'
import { useOrderEvents, type EventType, type Order, type OrderEvent } from '../api'
import { eventActor, eventTitle } from '../labels'
import { Notice } from './Notice'
import { SectionCard } from './SectionCard'

const dotTones: Partial<Record<EventType, string>> = {
  status_changed: 'bg-ink',
  created: 'bg-ink',
  payment_received: 'bg-accent',
  cod_collected: 'bg-accent',
  payment_link_expired: 'bg-amber',
  price_changed: 'bg-amber',
  notification_failed: 'bg-signal',
}

function NotificationFailedHint() {
  const { workspaceId, can } = useWorkspace()
  return (
    <p className="mt-1 text-[13px] text-signal">
      Buyers outside their 24-hour window only get updates through an approved template. Map one for this update in{' '}
      {can('admin') ? (
        <Link to={`/app/w/${workspaceId}/store`} className="font-medium underline underline-offset-4">
          Store settings
        </Link>
      ) : (
        'Store settings (ask an admin)'
      )}
      .
    </p>
  )
}

function TimelineEntry({ event, buyerName, timeZone }: { event: OrderEvent; buyerName: string; timeZone: string }) {
  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      <div aria-hidden="true" className="flex w-3 shrink-0 flex-col items-center">
        <span className={cn('mt-1.5 size-2.5 rounded-full ring-4 ring-card', dotTones[event.type] ?? 'bg-muted/50')} />
        <span className="timeline-line mt-1 w-px flex-1 bg-line" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink">{eventTitle(event)}</p>
        {event.detail && <p className="text-[13px] text-ink-2">{event.detail}</p>}
        {event.type === 'notification_failed' && <NotificationFailedHint />}
        <p className="mt-0.5 text-[12px] text-muted">
          {eventActor(event, buyerName)} · <time dateTime={event.created_at}>{formatDateTime(event.created_at, timeZone)}</time>
        </p>
      </div>
    </li>
  )
}

export function OrderTimeline({ order }: { order: Order }) {
  const { workspaceId, timeZone } = useWorkspace()
  const events = useOrderEvents(workspaceId, order.id)

  return (
    <SectionCard title="Timeline">
      {events.isPending ? (
        <div className="flex flex-col gap-4" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : events.isError ? (
        <Notice
          tone="error"
          title="Couldn't load the timeline"
          action={
            <Button size="sm" variant="secondary" onClick={() => void events.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(events.error)}
        </Notice>
      ) : events.items.length === 0 ? (
        <p className="text-sm text-muted">Nothing has happened yet.</p>
      ) : (
        <>
          <ol aria-label="Order events" className="[&>li:last-child_.timeline-line]:hidden">
            {events.items.map((event) => (
              <TimelineEntry key={event.id} event={event} buyerName={order.contact.name} timeZone={timeZone} />
            ))}
          </ol>
          {events.hasNextPage && (
            <Button className="mt-4" size="sm" variant="secondary" loading={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()}>
              Show later events
            </Button>
          )}
        </>
      )}
    </SectionCard>
  )
}
