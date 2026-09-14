import { FileText, Plus, RefreshCw, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { errorMessage } from '../../../api/errors'
import type { MessageTemplate, TemplateCategory, TemplateStatus } from '../../../api/types'
import {
  Button,
  buttonClasses,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  type Column,
} from '../../../components/app'
import { formatRelative } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { useSyncTemplates, useTemplateList, type TemplateFilters } from './api'
import { CategoryBadge, QualityBadge, RejectionNotice } from './components/TemplateBadges'
import { categoryOptions, languageLabel, languageOptions, statusFilterOptions } from './lib/constants'

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

const statusValues = new Set<string>(statusFilterOptions.map((option) => option.value))
const categoryValues = new Set<string>(categoryOptions.map((option) => option.value))

export function TemplatesListPage() {
  const { can } = useWorkspace()
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('search') ?? '')
  const debouncedSearch = useDebounced(search.trim().toLowerCase(), 300)
  const sync = useSyncTemplates()
  const canManage = can('admin')

  const status = params.get('status') ?? ''
  const category = params.get('category') ?? ''
  const language = params.get('language') ?? ''
  const filters: TemplateFilters = {
    status: statusValues.has(status) ? (status as TemplateStatus) : undefined,
    category: categoryValues.has(category) ? (category as TemplateCategory) : undefined,
    language: language || undefined,
    search: debouncedSearch || undefined,
  }
  const filtered = Boolean(filters.status || filters.category || filters.language || filters.search)
  const list = useTemplateList(filters)

  const setFilter = (key: string, value: string) => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set(key, value)
        else next.delete(key)
        return next
      },
      { replace: true },
    )
  }

  const clearFilters = () => {
    setSearch('')
    setParams(new URLSearchParams(), { replace: true })
  }

  const columns: Column<MessageTemplate>[] = [
    {
      id: 'name',
      header: 'Name',
      className: 'min-w-[14rem] max-w-[26rem]',
      cell: (template) => (
        <div className="flex flex-col gap-1">
          <Link to={template.id} className="break-all font-mono text-[13px] font-medium text-ink underline-offset-2 hover:underline">
            {template.name}
          </Link>
          <span className="text-[12px] text-muted sm:hidden">
            {languageLabel(template.language)} · <StatusBadge status={template.status} />
          </span>
          {template.status === 'REJECTED' && <RejectionNotice reason={template.rejected_reason} compact />}
        </div>
      ),
    },
    { id: 'language', header: 'Language', hideOnMobile: true, cell: (template) => <span className="whitespace-nowrap">{languageLabel(template.language)}</span> },
    { id: 'category', header: 'Category', hideOnMobile: true, cell: (template) => <CategoryBadge category={template.category} /> },
    { id: 'status', header: 'Status', hideOnMobile: true, cell: (template) => <StatusBadge status={template.status} /> },
    { id: 'quality', header: 'Quality', hideOnMobile: true, cell: (template) => <QualityBadge score={template.quality_score} /> },
    {
      id: 'updated',
      header: 'Updated',
      hideOnMobile: true,
      cell: (template) => (
        <time dateTime={template.updated_at} className="whitespace-nowrap text-[13px] text-muted">
          {formatRelative(template.updated_at)}
        </time>
      ),
    },
  ]

  const syncMessage = sync.isSuccess
    ? sync.data.queued.length
      ? `Sync started for ${sync.data.queued.length} WhatsApp ${sync.data.queued.length === 1 ? 'account' : 'accounts'}. Statuses update here as Meta responds.`
      : 'No connected WhatsApp account to sync. Connect or reconnect WhatsApp first.'
    : sync.isError
      ? `Sync failed: ${errorMessage(sync.error)}`
      : ''

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Templates"
        description="Meta-approved templates let you message customers outside the 24-hour customer service window and power campaigns and automations."
        actions={
          canManage && (
            <>
              <Button
                variant="secondary"
                loading={sync.isPending}
                icon={<RefreshCw className="size-4" aria-hidden="true" />}
                onClick={() => sync.mutate()}
              >
                Sync from Meta
              </Button>
              <Link to="new" className={buttonClasses('primary')}>
                <Plus className="size-4" aria-hidden="true" />
                New template
              </Link>
            </>
          )
        }
      />

      <p aria-live="polite" className={syncMessage ? 'text-[13px] text-muted' : 'sr-only'}>
        {syncMessage}
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.5fr)_repeat(3,minmax(0,1fr))]">
        <Field label="Search by name">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden="true" />
            <Input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="order_shipped" className="pl-9" />
          </div>
        </Field>
        <Field label="Status">
          <Select value={filters.status ?? ''} onChange={(event) => setFilter('status', event.target.value)} placeholder="All statuses" options={statusFilterOptions} />
        </Field>
        <Field label="Category">
          <Select value={filters.category ?? ''} onChange={(event) => setFilter('category', event.target.value)} placeholder="All categories" options={categoryOptions} />
        </Field>
        <Field label="Language">
          <Select
            value={language}
            onChange={(event) => setFilter('language', event.target.value)}
            placeholder="All languages"
            options={languageOptions.map((option) => ({ value: option.value, label: `${option.label} (${option.value})` }))}
          />
        </Field>
      </div>

      {list.isError ? (
        <EmptyState
          icon={<FileText />}
          title="Couldn't load templates"
          description={errorMessage(list.error)}
          action={
            <Button variant="secondary" onClick={() => void list.refetch()}>
              Try again
            </Button>
          }
        />
      ) : (
        <Table
          caption="Message templates"
          columns={columns}
          rows={list.items}
          getRowId={(template) => template.id}
          loading={list.isPending}
          hasNextPage={list.hasNextPage}
          isFetchingNextPage={list.isFetchingNextPage}
          onLoadMore={() => void list.fetchNextPage()}
          empty={
            filtered ? (
              <EmptyState
                icon={<Search />}
                title="No templates match these filters"
                action={
                  <Button variant="secondary" onClick={clearFilters}>
                    Clear filters
                  </Button>
                }
              />
            ) : (
              <EmptyState
                icon={<FileText />}
                title="No templates yet"
                description={
                  canManage
                    ? 'Create your first template, or sync templates you already made in Meta Business Manager.'
                    : 'An admin can create templates or sync them from Meta.'
                }
                action={
                  canManage && (
                    <Link to="new" className={buttonClasses('primary')}>
                      New template
                    </Link>
                  )
                }
              />
            )
          }
        />
      )}
    </div>
  )
}
