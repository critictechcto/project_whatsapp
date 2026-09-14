import { ArrowLeft, FileSpreadsheet, TriangleAlert, Upload } from 'lucide-react'
import { useEffect } from 'react'
import { Link } from 'react-router'
import { api, unwrap } from '../../../../api/client'
import { useCursorQuery } from '../../../../api/pagination'
import { Button, buttonClasses, EmptyState, PageHeader, Table, type Column } from '../../../../components/app'
import { formatDateTime } from '../../../../lib/datetime'
import { formatNumber } from '../../../../lib/format'
import { useWorkspace } from '../../../../lib/workspace'
import { contactKeys, importInProgress } from '../api'
import { ImportStatusBadge } from '../components/ImportStatusBadge'
import type { ContactImport } from '../lib/types'

export function ImportsPage() {
  const { workspaceId, timeZone, can } = useWorkspace()
  const base = `/app/w/${workspaceId}`
  const imports = useCursorQuery<ContactImport>({
    queryKey: contactKeys.custom(workspaceId, 'imports', 'list'),
    queryFn: ({ cursor, signal }) => unwrap(api.GET('/api/v1/contacts/imports/', { params: { query: { cursor } }, signal })),
  })
  const anyRunning = imports.items.some(importInProgress)

  const columns: Column<ContactImport>[] = [
    {
      id: 'file',
      header: 'File',
      cell: (job) => (
        <Link to={`${base}/contacts/imports/${job.id}`} className="font-medium text-ink underline-offset-2 hover:underline">
          {job.file_name || 'Untitled file'}
        </Link>
      ),
    },
    { id: 'status', header: 'Status', cell: (job) => <ImportStatusBadge status={job.status} /> },
    { id: 'rows', header: 'Rows', align: 'right', hideOnMobile: true, cell: (job) => formatNumber(job.total_rows) },
    {
      id: 'result',
      header: 'Created / updated',
      hideOnMobile: true,
      align: 'right',
      cell: (job) => `${formatNumber(job.created_count)} / ${formatNumber(job.updated_count)}`,
    },
    { id: 'errors', header: 'Errors', align: 'right', hideOnMobile: true, cell: (job) => formatNumber(job.error_count) },
    { id: 'created', header: 'Uploaded', hideOnMobile: true, cell: (job) => formatDateTime(job.created_at, timeZone) },
  ]

  return (
    <div className="flex flex-col gap-6">
      <Link to={`${base}/contacts`} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden="true" />
        Contacts
      </Link>
      <PageHeader
        title="Contact imports"
        description="CSV uploads and their results."
        actions={
          can('admin') && (
            <Link to={`${base}/contacts/imports/new`} className={buttonClasses('primary')}>
              <Upload className="size-4" aria-hidden="true" />
              New import
            </Link>
          )
        }
      />
      {anyRunning && <ImportsPoller refetch={() => void imports.refetch()} />}
      {imports.isError ? (
        <EmptyState
          icon={<TriangleAlert />}
          title="Imports didn't load"
          action={
            <Button variant="secondary" onClick={() => void imports.refetch()}>
              Try again
            </Button>
          }
        />
      ) : (
        <Table
          caption="Contact imports"
          columns={columns}
          rows={imports.items}
          getRowId={(job) => job.id}
          loading={imports.isLoading}
          hasNextPage={imports.hasNextPage}
          isFetchingNextPage={imports.isFetchingNextPage}
          onLoadMore={() => void imports.fetchNextPage()}
          empty={
            <EmptyState
              icon={<FileSpreadsheet />}
              title="No imports yet"
              description="Upload a CSV with a phone column to add many contacts at once."
              action={
                can('admin') ? (
                  <Link to={`${base}/contacts/imports/new`} className={buttonClasses('primary')}>
                    Import CSV
                  </Link>
                ) : undefined
              }
            />
          }
        />
      )}
    </div>
  )
}

/** Refreshes the list every few seconds while an import is still running. */
function ImportsPoller({ refetch }: { refetch: () => void }) {
  useEffect(() => {
    const timer = setInterval(refetch, 4000)
    return () => clearInterval(timer)
  }, [refetch])
  return null
}
