import { Search, TriangleAlert, Upload, UserPlus, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { api, unwrap } from '../../../../api/client'
import { useCursorQuery } from '../../../../api/pagination'
import {
  Button,
  buttonClasses,
  Checkbox,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Select,
  Skeleton,
  useToast,
} from '../../../../components/app'
import { formatDate, formatDateTime, formatRelative } from '../../../../lib/datetime'
import { formatNumber } from '../../../../lib/format'
import { useWorkspace } from '../../../../lib/workspace'
import { contactKeys, useInvalidateContacts, useTags } from '../api'
import { BulkTagDialog } from '../components/BulkTagDialog'
import { ContactFormDialog } from '../components/ContactFormDialog'
import { ConfirmDialog, OptInBadge, TagList, TagPicker } from '../components/shared'
import { optInInfo, optInStatuses } from '../lib/consent'
import { formatPhone } from '../lib/phone'
import type { Contact, OptInStatus, Tag } from '../lib/types'
import { useDebouncedValue } from '../lib/useDebouncedValue'
import { useMediaQuery } from '../lib/useMediaQuery'

const isOptInStatus = (value: string): value is OptInStatus => (optInStatuses as readonly string[]).includes(value)

const EMPTY_SELECTION: ReadonlySet<string> = new Set()

export function ContactsListPage() {
  const { workspaceId, timeZone, can } = useWorkspace()
  const base = `/app/w/${workspaceId}`
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const tagIds = params.getAll('tag')
  const rawStatus = params.get('status') ?? ''
  const status = isOptInStatus(rawStatus) ? rawStatus : undefined
  const hasFilters = Boolean(q || tagIds.length || status)

  const canWrite = can('agent')
  const canDelete = can('admin')
  const compact = useMediaQuery('(max-width: 767px)')
  const { tags, tagMap, isLoading: tagsLoading } = useTags()
  const invalidate = useInvalidateContacts()
  const { toast } = useToast()

  const [searchText, setSearchText] = useState(q)
  const debouncedSearch = useDebouncedValue(searchText.trim(), 300)

  const updateParams = (update: (next: URLSearchParams) => void) =>
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous)
        update(next)
        return next
      },
      { replace: true },
    )

  useEffect(() => {
    if (debouncedSearch === q) return
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous)
        if (debouncedSearch) next.set('q', debouncedSearch)
        else next.delete('q')
        return next
      },
      { replace: true },
    )
    // Only the debounced text drives the URL; `q` changes as a result.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch])

  // The API filters by one tag; extra selected tags narrow the loaded rows ("has all tags").
  const serverTag = tagIds[0]
  const contacts = useCursorQuery<Contact>({
    queryKey: contactKeys.list(workspaceId, { q, tag: serverTag ?? '', status: status ?? '' }),
    queryFn: ({ cursor, signal }) =>
      unwrap(
        api.GET('/api/v1/contacts/', {
          params: { query: { cursor, page_size: 50, search: q || undefined, tag: serverTag, marketing_opt_in_status: status } },
          signal,
        }),
      ),
  })
  const rows = useMemo(
    () => (tagIds.length > 1 ? contacts.items.filter((contact) => tagIds.every((id) => contact.tags?.includes(id))) : contacts.items),
    [contacts.items, tagIds],
  )

  const filterKey = `${q}|${tagIds.join(',')}|${status ?? ''}`
  const [selection, setSelection] = useState<{ key: string; ids: ReadonlySet<string> }>({ key: filterKey, ids: EMPTY_SELECTION })
  const selected = selection.key === filterKey ? selection.ids : EMPTY_SELECTION
  const selectedIds = rows.filter((row) => selected.has(row.id)).map((row) => row.id)
  const setSelected = (ids: ReadonlySet<string>) => setSelection({ key: filterKey, ids })
  const toggle = (id: string, checked: boolean) => {
    const next = new Set(selected)
    if (checked) next.add(id)
    else next.delete(id)
    setSelected(next)
  }
  const allSelected = rows.length > 0 && selectedIds.length === rows.length
  const clearSelection = () => setSelected(EMPTY_SELECTION)

  const [createOpen, setCreateOpen] = useState(false)
  const [bulkMode, setBulkMode] = useState<'add' | 'remove' | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const deleteSelected = async () => {
    setDeleting(true)
    const results = await Promise.allSettled(
      selectedIds.map((id) => unwrap(api.DELETE('/api/v1/contacts/{id}/', { params: { path: { id } } }))),
    )
    const failed = results.filter((result) => result.status === 'rejected').length
    const deleted = results.length - failed
    setDeleting(false)
    setDeleteOpen(false)
    clearSelection()
    void invalidate()
    if (deleted) toast({ title: `Deleted ${formatNumber(deleted)} ${deleted === 1 ? 'contact' : 'contacts'}`, tone: 'success' })
    if (failed) toast({ title: `${formatNumber(failed)} ${failed === 1 ? 'contact' : 'contacts'} could not be deleted`, tone: 'error' })
  }

  const clearFilters = () => {
    setSearchText('')
    updateParams((next) => {
      next.delete('q')
      next.delete('tag')
      next.delete('status')
    })
  }

  const headerActions = (
    <>
      <Link to={`${base}/contacts/tags`} className={buttonClasses('secondary')}>
        Tags
      </Link>
      {canDelete ? (
        <Link to={`${base}/contacts/imports/new`} className={buttonClasses('secondary')}>
          <Upload className="size-4" aria-hidden="true" />
          Import CSV
        </Link>
      ) : (
        canWrite && (
          <Link to={`${base}/contacts/imports`} className={buttonClasses('secondary')}>
            Imports
          </Link>
        )
      )}
      {canWrite && (
        <Button icon={<UserPlus className="size-4" aria-hidden="true" />} onClick={() => setCreateOpen(true)}>
          Add contact
        </Button>
      )}
    </>
  )

  const loading = contacts.isLoading
  let body: React.ReactNode
  if (contacts.isError) {
    body = (
      <EmptyState
        icon={<TriangleAlert />}
        title="Contacts didn't load"
        description="Check your connection and try again."
        action={
          <Button variant="secondary" onClick={() => void contacts.refetch()}>
            Try again
          </Button>
        }
      />
    )
  } else if (!loading && rows.length === 0 && !contacts.hasNextPage) {
    body = hasFilters ? (
      <EmptyState
        icon={<Search />}
        title="No contacts match these filters"
        description="Try a different search, tag or opt-in status."
        action={
          <Button variant="secondary" onClick={clearFilters}>
            Clear filters
          </Button>
        }
      />
    ) : (
      <EmptyState
        icon={<Users />}
        title="No contacts yet"
        description="Add contacts one by one or import a CSV of customers who agreed to hear from you on WhatsApp."
        action={
          canWrite ? (
            <div className="flex flex-wrap justify-center gap-2">
              {canDelete && (
                <Link to={`${base}/contacts/imports/new`} className={buttonClasses('secondary')}>
                  Import CSV
                </Link>
              )}
              <Button onClick={() => setCreateOpen(true)}>Add contact</Button>
            </div>
          ) : undefined
        }
      />
    )
  } else {
    const listProps = {
      rows,
      loading,
      tagMap,
      timeZone,
      base,
      selectable: canWrite,
      selected,
      allSelected,
      someSelected: selectedIds.length > 0,
      onToggle: toggle,
      onToggleAll: (checked: boolean) => setSelected(checked ? new Set(rows.map((row) => row.id)) : EMPTY_SELECTION),
    }
    body = (
      <div className="overflow-hidden rounded-xl border border-line bg-card">
        {compact ? <ContactCards {...listProps} /> : <ContactTable {...listProps} />}
        {(contacts.hasNextPage || contacts.isFetchingNextPage) && (
          <div className="flex flex-col items-center gap-1 border-t border-line-2 p-3">
            <Button variant="secondary" size="sm" loading={contacts.isFetchingNextPage} onClick={() => void contacts.fetchNextPage()}>
              Load more
            </Button>
            {tagIds.length > 1 && rows.length === 0 && <p className="text-[12.5px] text-muted">No matches in the contacts loaded so far.</p>}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Contacts"
        description="People you can message on WhatsApp, with their tags and marketing consent."
        actions={headerActions}
      />

      <section aria-label="Filters" className="flex flex-col gap-3 lg:flex-row lg:items-end">
        <Field label="Search contacts" hideLabel className="lg:w-80">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden="true" />
            <Input
              type="search"
              className="pl-9"
              placeholder="Search name, phone or email"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />
          </div>
        </Field>
        <div className="grid gap-3 sm:grid-cols-2 lg:flex lg:flex-1 lg:items-end">
          <TagPicker
            aria-label="Filter by tags"
            placeholder="Filter by tags"
            tags={tags}
            loading={tagsLoading}
            value={tagIds}
            className="lg:min-w-64 lg:flex-1"
            onChange={(value) =>
              updateParams((next) => {
                next.delete('tag')
                for (const id of value) next.append('tag', id)
              })
            }
          />
          <Field label="Marketing opt-in" hideLabel className="lg:w-48">
            <Select
              value={status ?? ''}
              onChange={(event) =>
                updateParams((next) => {
                  if (event.target.value) next.set('status', event.target.value)
                  else next.delete('status')
                })
              }
            >
              <option value="">Any opt-in status</option>
              {optInStatuses.map((value) => (
                <option key={value} value={value}>
                  {optInInfo[value].label}
                </option>
              ))}
            </Select>
          </Field>
          {hasFilters && (
            <Button variant="ghost" onClick={clearFilters}>
              Clear filters
            </Button>
          )}
        </div>
      </section>
      {tagIds.length > 1 && <p className="-mt-3 text-[13px] text-muted">Showing contacts that have all selected tags.</p>}

      {selectedIds.length > 0 && (
        <div
          role="region"
          aria-label="Bulk actions"
          className="sticky top-2 z-10 flex flex-wrap items-center gap-2 rounded-lg border border-line bg-ink px-3 py-2 text-paper shadow-md"
        >
          <p className="mr-auto text-sm" aria-live="polite">
            {formatNumber(selectedIds.length)} selected
          </p>
          <Button size="sm" variant="secondary" onClick={() => setBulkMode('add')}>
            Add tags
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setBulkMode('remove')}>
            Remove tags
          </Button>
          {canDelete && (
            <Button size="sm" variant="danger" onClick={() => setDeleteOpen(true)}>
              Delete
            </Button>
          )}
          <Button size="sm" variant="ghost" className="text-paper hover:bg-paper/10" onClick={clearSelection}>
            Clear selection
          </Button>
        </div>
      )}

      {body}

      <ContactFormDialog open={createOpen} onOpenChange={setCreateOpen} />
      <BulkTagDialog
        open={bulkMode !== null}
        onOpenChange={(open) => !open && setBulkMode(null)}
        mode={bulkMode ?? 'add'}
        contactIds={selectedIds}
        onDone={clearSelection}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        danger
        loading={deleting}
        title={`Delete ${formatNumber(selectedIds.length)} ${selectedIds.length === 1 ? 'contact' : 'contacts'}?`}
        description="Their consent history is deleted with them. This can't be undone."
        confirmLabel="Delete"
        onConfirm={() => void deleteSelected()}
      />
    </div>
  )
}

type ListProps = {
  rows: readonly Contact[]
  loading: boolean
  tagMap: Map<string, Tag>
  timeZone: string
  base: string
  selectable: boolean
  selected: ReadonlySet<string>
  allSelected: boolean
  someSelected: boolean
  onToggle: (id: string, checked: boolean) => void
  onToggleAll: (checked: boolean) => void
}

const contactLabel = (contact: Contact) => contact.name || formatPhone(contact.phone_e164)

function ContactName({ contact, base }: { contact: Contact; base: string }) {
  return (
    <Link to={`${base}/contacts/${contact.id}`} className="font-medium text-ink underline-offset-2 hover:underline">
      {contact.name || <span className="text-muted">Unnamed contact</span>}
    </Link>
  )
}

function LastInbound({ iso, timeZone }: { iso: string | null; timeZone: string }) {
  if (!iso) return <span className="text-muted">Never</span>
  return (
    <time dateTime={iso} title={formatDateTime(iso, timeZone)}>
      {formatRelative(iso)}
    </time>
  )
}

function ContactTable({ rows, loading, tagMap, timeZone, base, selectable, selected, allSelected, someSelected, onToggle, onToggleAll }: ListProps) {
  const th = 'px-4 py-2.5 text-left font-mono text-[11px] font-normal uppercase tracking-[0.12em] text-muted'
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Contacts</caption>
        <thead>
          <tr className="border-b border-line-2 bg-paper/60">
            {selectable && (
              <th scope="col" className="w-10 py-2.5 pl-4">
                <input
                  type="checkbox"
                  aria-label="Select all shown contacts"
                  className="size-4 cursor-pointer accent-accent"
                  checked={allSelected}
                  ref={(node) => {
                    if (node) node.indeterminate = someSelected && !allSelected
                  }}
                  onChange={(event) => onToggleAll(event.target.checked)}
                  disabled={rows.length === 0}
                />
              </th>
            )}
            <th scope="col" className={th}>Name</th>
            <th scope="col" className={th}>Phone</th>
            <th scope="col" className={th}>Tags</th>
            <th scope="col" className={th}>Marketing</th>
            <th scope="col" className={`${th} hidden lg:table-cell`}>Last inbound</th>
            <th scope="col" className={`${th} hidden lg:table-cell`}>Created</th>
          </tr>
        </thead>
        <tbody aria-busy={loading || undefined}>
          {loading && rows.length === 0
            ? Array.from({ length: 6 }, (_, i) => (
                <tr key={i} className="border-b border-line-2 last:border-b-0">
                  {Array.from({ length: selectable ? 7 : 6 }, (__, j) => (
                    <td key={j} className="px-4 py-3">
                      <Skeleton className="h-4 w-3/4" />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((contact) => {
                const isSelected = selected.has(contact.id)
                return (
                  <tr key={contact.id} className={`border-b border-line-2 last:border-b-0 ${isSelected ? 'bg-accent-soft/40' : 'hover:bg-paper/50'}`}>
                    {selectable && (
                      <td className="py-3 pl-4 align-middle">
                        <input
                          type="checkbox"
                          aria-label={`Select ${contactLabel(contact)}`}
                          className="size-4 cursor-pointer accent-accent"
                          checked={isSelected}
                          onChange={(event) => onToggle(contact.id, event.target.checked)}
                        />
                      </td>
                    )}
                    <td className="px-4 py-3 align-middle">
                      <ContactName contact={contact} base={base} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 align-middle font-mono text-[13px] text-ink-2">{formatPhone(contact.phone_e164)}</td>
                    <td className="px-4 py-3 align-middle">
                      <TagList tagIds={contact.tags ?? []} tagMap={tagMap} max={3} empty={<span className="text-muted">—</span>} />
                    </td>
                    <td className="px-4 py-3 align-middle">
                      <OptInBadge status={contact.marketing_opt_in_status} />
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 align-middle text-ink-2 lg:table-cell">
                      <LastInbound iso={contact.last_inbound_at} timeZone={timeZone} />
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 align-middle text-ink-2 lg:table-cell">{formatDate(contact.created_at, timeZone)}</td>
                  </tr>
                )
              })}
        </tbody>
      </table>
    </div>
  )
}

function ContactCards({ rows, loading, tagMap, timeZone, base, selectable, selected, allSelected, onToggle, onToggleAll }: ListProps) {
  if (loading && rows.length === 0) {
    return (
      <ul aria-busy="true" className="divide-y divide-line-2">
        {Array.from({ length: 4 }, (_, i) => (
          <li key={i} className="flex flex-col gap-2 p-4">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-2/3" />
          </li>
        ))}
      </ul>
    )
  }
  return (
    <>
      {selectable && (
        <div className="border-b border-line-2 bg-paper/60 px-4 py-2.5">
          <Checkbox label="Select all shown" checked={allSelected} onChange={(event) => onToggleAll(event.target.checked)} />
        </div>
      )}
      <ul aria-label="Contacts" className="divide-y divide-line-2">
        {rows.map((contact) => (
          <li key={contact.id} className="flex gap-3 p-4">
            {selectable && (
              <input
                type="checkbox"
                aria-label={`Select ${contactLabel(contact)}`}
                className="mt-1 size-4 shrink-0 cursor-pointer accent-accent"
                checked={selected.has(contact.id)}
                onChange={(event) => onToggle(contact.id, event.target.checked)}
              />
            )}
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <ContactName contact={contact} base={base} />
                <OptInBadge status={contact.marketing_opt_in_status} />
              </div>
              <p className="font-mono text-[13px] text-ink-2">{formatPhone(contact.phone_e164)}</p>
              <TagList tagIds={contact.tags ?? []} tagMap={tagMap} max={4} />
              <p className="text-[12.5px] text-muted">
                Last inbound <LastInbound iso={contact.last_inbound_at} timeZone={timeZone} /> · Added {formatDate(contact.created_at, timeZone)}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}
