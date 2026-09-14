import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, MessageCircle, Pencil, Trash2, TriangleAlert, UserX } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { api, unwrap } from '../../../../api/client'
import { errorMessage, isApiError } from '../../../../api/errors'
import { useCursorQuery } from '../../../../api/pagination'
import { Button, buttonClasses, EmptyState, PageHeader, PageSpinner, Skeleton, useToast } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { formatDateTime, formatRelative, timeZoneName } from '../../../../lib/datetime'
import { useWorkspace } from '../../../../lib/workspace'
import { contactKeys, useInvalidateContacts, useMemberNames, useTags } from '../api'
import { ConsentDialog } from '../components/ConsentDialog'
import { ContactFormDialog } from '../components/ContactFormDialog'
import { ConfirmDialog, OptInBadge, TagList } from '../components/shared'
import { consentActionLabels, consentSourceLabel, optInInfo, optInSourceLabel } from '../lib/consent'
import { formatPhone } from '../lib/phone'
import type { ConsentEvent, Contact } from '../lib/types'

export function ContactDetailPage() {
  const { contactId = '' } = useParams()
  const { workspaceId } = useWorkspace()
  const base = `/app/w/${workspaceId}`

  const contact = useQuery({
    queryKey: contactKeys.detail(workspaceId, contactId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/contacts/{id}/', { params: { path: { id: contactId } }, signal })),
  })

  const back = (
    <Link to={`${base}/contacts`} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
      <ArrowLeft className="size-4" aria-hidden="true" />
      Contacts
    </Link>
  )

  if (contact.isLoading) return <PageSpinner label="Loading contact" />
  if (contact.isError || !contact.data) {
    const missing = isApiError(contact.error) && contact.error.status === 404
    return (
      <div className="flex flex-col gap-6">
        {back}
        <EmptyState
          icon={missing ? <UserX /> : <TriangleAlert />}
          title={missing ? 'Contact not found' : "This contact didn't load"}
          description={missing ? 'It may have been deleted, or it belongs to another workspace.' : errorMessage(contact.error)}
          action={
            missing ? undefined : (
              <Button variant="secondary" onClick={() => void contact.refetch()}>
                Try again
              </Button>
            )
          }
        />
      </div>
    )
  }

  return <ContactDetail contact={contact.data} back={back} />
}

function ContactDetail({ contact, back }: { contact: Contact; back: React.ReactNode }) {
  const { workspaceId, timeZone, can } = useWorkspace()
  const base = `/app/w/${workspaceId}`
  const navigate = useNavigate()
  const { toast } = useToast()
  const invalidate = useInvalidateContacts()
  const { tagMap } = useTags()
  const [editOpen, setEditOpen] = useState(false)
  const [consentAction, setConsentAction] = useState<'opt_in' | 'opt_out' | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE('/api/v1/contacts/{id}/', { params: { path: { id: contact.id } } })),
    onSuccess: () => {
      void invalidate()
      toast({ title: 'Contact deleted', tone: 'success' })
      navigate(`${base}/contacts`, { replace: true })
    },
    onError: (error) => {
      setDeleteOpen(false)
      toast({ title: "Couldn't delete the contact", description: errorMessage(error), tone: 'error' })
    },
  })

  const phone = formatPhone(contact.phone_e164)
  const status = contact.marketing_opt_in_status
  const attributes = Object.entries(contact.attributes ?? {})

  return (
    <div className="flex flex-col gap-6">
      {back}
      <PageHeader
        eyebrow="Contact"
        title={contact.name || phone}
        description={contact.name ? <span className="font-mono">{phone}</span> : undefined}
        actions={
          <>
            <ConversationAction contact={contact} />
            {can('agent') && (
              <Button variant="secondary" icon={<Pencil className="size-4" aria-hidden="true" />} onClick={() => setEditOpen(true)}>
                Edit
              </Button>
            )}
            {can('admin') && (
              <Button variant="ghost" className="text-signal" icon={<Trash2 className="size-4" aria-hidden="true" />} onClick={() => setDeleteOpen(true)}>
                Delete
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-2">
          <Card title="Profile">
            <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
              <Detail label="Phone">
                <span className="font-mono">{phone}</span>
              </Detail>
              <Detail label="WhatsApp ID">
                <span className="font-mono">{contact.wa_id}</span>
              </Detail>
              <Detail label="Email">{contact.email || <span className="text-muted">Not added</span>}</Detail>
              <Detail label="Last message from them">
                {contact.last_inbound_at ? (
                  <time dateTime={contact.last_inbound_at} title={formatDateTime(contact.last_inbound_at, timeZone)}>
                    {formatRelative(contact.last_inbound_at)}
                  </time>
                ) : (
                  <span className="text-muted">Never</span>
                )}
              </Detail>
              <Detail label="Added">{formatDateTime(contact.created_at, timeZone)}</Detail>
              <Detail label="Updated">{formatDateTime(contact.updated_at, timeZone)}</Detail>
            </dl>
          </Card>

          <Card title="Attributes">
            {attributes.length ? (
              <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                {attributes.map(([key, value]) => (
                  <Detail key={key} label={key} mono>
                    {typeof value === 'string' ? value : JSON.stringify(value)}
                  </Detail>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-muted">No custom attributes.</p>
            )}
          </Card>

          <ConsentHistory contact={contact} />
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <Card title="Marketing consent">
            <div className="flex flex-col gap-3 text-sm">
              <div>
                <OptInBadge status={status} />
              </div>
              <p className="text-muted">{optInInfo[status].explanation}</p>
              <dl className="grid gap-2">
                {contact.opted_in_at && (
                  <Detail label="Opted in">
                    {formatDateTime(contact.opted_in_at, timeZone)}
                    {contact.opt_in_source && <span className="text-muted"> · {optInSourceLabel(contact.opt_in_source)}</span>}
                  </Detail>
                )}
                {contact.opted_out_at && <Detail label="Opted out">{formatDateTime(contact.opted_out_at, timeZone)}</Detail>}
              </dl>
              {can('agent') && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {status !== 'opted_in' && (
                    <Button size="sm" variant="secondary" onClick={() => setConsentAction('opt_in')}>
                      Record opt-in
                    </Button>
                  )}
                  {status !== 'opted_out' && (
                    <Button size="sm" variant="secondary" onClick={() => setConsentAction('opt_out')}>
                      Record opt-out
                    </Button>
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card title="Tags">
            <TagList tagIds={contact.tags ?? []} tagMap={tagMap} empty={<p className="text-sm text-muted">No tags.</p>} />
          </Card>
        </div>
      </div>

      <ContactFormDialog open={editOpen} onOpenChange={setEditOpen} contact={contact} />
      <ConsentDialog
        open={consentAction !== null}
        onOpenChange={(open) => !open && setConsentAction(null)}
        contact={contact}
        action={consentAction ?? 'opt_in'}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        danger
        loading={remove.isPending}
        title="Delete this contact?"
        description="Their tags and consent history are deleted with them. This can't be undone."
        confirmLabel="Delete contact"
        onConfirm={() => remove.mutate()}
      />
    </div>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="rounded-xl border border-line bg-card">
      <h2 className="border-b border-line-2 px-5 py-3 font-display text-base font-semibold tracking-[-0.01em] text-ink">{title}</h2>
      <div className="px-5 py-4">{children}</div>
    </section>
  )
}

function Detail({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className={cn('text-[12px] text-muted', mono ? 'font-mono' : 'font-mono uppercase tracking-[0.1em]')}>{label}</dt>
      <dd className="mt-0.5 break-words text-ink">{children}</dd>
    </div>
  )
}

/** Links to the contact's conversation, or starts one (agent+) when none exists. */
function ConversationAction({ contact }: { contact: Contact }) {
  const { workspaceId, can } = useWorkspace()
  const navigate = useNavigate()
  const { toast } = useToast()
  const inbox = `/app/w/${workspaceId}/inbox`

  const lookup = useQuery({
    queryKey: contactKeys.custom(workspaceId, 'detail', contact.id, 'conversation'),
    queryFn: async ({ signal }) => {
      const page = await unwrap(
        api.GET('/api/v1/inbox/conversations/', { params: { query: { search: contact.phone_e164, page_size: 20 } }, signal }),
      )
      return page.results.find((conversation) => conversation.contact.id === contact.id)?.id ?? null
    },
  })

  const start = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/inbox/conversations/', { body: { contact_id: contact.id } })),
    onSuccess: (conversation) => navigate(`${inbox}/${conversation.id}`),
    onError: (error) => toast({ title: "Couldn't start a conversation", description: errorMessage(error), tone: 'error' }),
  })

  if (lookup.isLoading) return <Skeleton className="h-10 w-40" />
  if (lookup.data) {
    return (
      <Link to={`${inbox}/${lookup.data}`} className={buttonClasses('primary')}>
        <MessageCircle className="size-4" aria-hidden="true" />
        Open conversation
      </Link>
    )
  }
  if (!can('agent')) return null
  return (
    <Button icon={<MessageCircle className="size-4" aria-hidden="true" />} loading={start.isPending} onClick={() => start.mutate()}>
      Start conversation
    </Button>
  )
}

function ConsentHistory({ contact }: { contact: Contact }) {
  const { workspaceId, timeZone } = useWorkspace()
  const names = useMemberNames()
  const events = useCursorQuery<ConsentEvent>({
    queryKey: contactKeys.custom(workspaceId, 'detail', contact.id, 'consent-events'),
    queryFn: ({ cursor, signal }) =>
      unwrap(api.GET('/api/v1/contacts/{id}/consent-events/', { params: { path: { id: contact.id }, query: { cursor, page_size: 50 } }, signal })),
  })
  const zone = timeZoneName(timeZone)

  const who = (event: ConsentEvent) => {
    if (event.actor) return names.get(event.actor) ?? 'a team member'
    if (event.source === 'whatsapp_keyword' || event.source === 'meta_marketing_optout') return 'the contact'
    return null
  }

  return (
    <Card title="Consent history">
      {events.isLoading ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      ) : events.isError ? (
        <div className="flex flex-wrap items-center gap-3 text-sm text-signal">
          Consent history didn't load.
          <Button size="sm" variant="secondary" onClick={() => void events.refetch()}>
            Try again
          </Button>
        </div>
      ) : events.items.length === 0 ? (
        <p className="text-sm text-muted">No consent changes recorded yet.</p>
      ) : (
        <>
          <ol aria-label="Consent history" className="relative flex flex-col gap-5 border-l border-line-2 pl-5">
            {events.items.map((event) => {
              const actor = who(event)
              return (
                <li key={event.id} className="relative">
                  <span
                    aria-hidden="true"
                    className={cn(
                      'absolute -left-[26px] top-1 size-3 rounded-full border-2 border-card',
                      event.action === 'opt_in' ? 'bg-accent' : 'bg-signal',
                    )}
                  />
                  <p className="text-sm font-medium text-ink">{consentActionLabels[event.action]}</p>
                  <p className="mt-0.5 text-[13px] text-muted">
                    {consentSourceLabel(event.source, event.action)}
                    {actor && ` · by ${actor}`}
                    {' · '}
                    <time dateTime={event.occurred_at}>
                      {formatDateTime(event.occurred_at, timeZone)} {zone}
                    </time>
                  </p>
                  {event.evidence && (
                    <p className="mt-1.5 rounded-md border border-line-2 bg-paper/60 px-3 py-2 text-[13px] text-ink-2">{event.evidence}</p>
                  )}
                </li>
              )
            })}
          </ol>
          {events.hasNextPage && (
            <Button className="mt-4" size="sm" variant="secondary" loading={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()}>
              Load older changes
            </Button>
          )}
        </>
      )}
    </Card>
  )
}
