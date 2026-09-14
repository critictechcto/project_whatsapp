import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CircleAlert, Download, TriangleAlert } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { api, unwrap } from '../../../../api/client'
import { errorMessage } from '../../../../api/errors'
import { Button, buttonClasses, EmptyState, PageHeader, PageSpinner } from '../../../../components/app'
import { formatDateTime } from '../../../../lib/datetime'
import { formatNumber } from '../../../../lib/format'
import { useWorkspace } from '../../../../lib/workspace'
import { contactKeys, importInProgress } from '../api'
import { ImportStatusBadge } from '../components/ImportStatusBadge'
import { errorsToCsv } from '../lib/csv'
import type { ContactImport } from '../lib/types'

export const IMPORT_POLL_MS = 1500

export function ImportStatusPage() {
  const { importId = '' } = useParams()
  const { workspaceId, timeZone, can } = useWorkspace()
  const base = `/app/w/${workspaceId}`
  const location = useLocation()
  const estimatedRows = (location.state as { estimatedRows?: number } | null)?.estimatedRows
  const queryClient = useQueryClient()

  const job = useQuery({
    queryKey: contactKeys.custom(workspaceId, 'imports', importId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/contacts/imports/{id}/', { params: { path: { id: importId } }, signal })),
    refetchInterval: (query) => (importInProgress(query.state.data) ? IMPORT_POLL_MS : false),
    staleTime: 0,
  })

  // Once the import finishes, refresh contact lists and tags that may now be out of date.
  const status = job.data?.status
  const wasRunning = useRef(false)
  useEffect(() => {
    if (status === 'queued' || status === 'processing') wasRunning.current = true
    else if (status && wasRunning.current) {
      wasRunning.current = false
      void queryClient.invalidateQueries({ queryKey: contactKeys.lists(workspaceId) })
      void queryClient.invalidateQueries({ queryKey: contactKeys.details(workspaceId) })
      void queryClient.invalidateQueries({ queryKey: contactKeys.custom(workspaceId, 'imports', 'list') })
    }
  }, [status, queryClient, workspaceId])

  const back = (
    <Link to={`${base}/contacts/imports`} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
      <ArrowLeft className="size-4" aria-hidden="true" />
      Imports
    </Link>
  )

  if (job.isLoading) return <PageSpinner label="Loading import" />
  if (job.isError || !job.data) {
    return (
      <div className="flex flex-col gap-6">
        {back}
        <EmptyState icon={<TriangleAlert />} title="This import didn't load" description={errorMessage(job.error)} />
      </div>
    )
  }

  const data = job.data
  return (
    <div className="flex flex-col gap-6">
      {back}
      <PageHeader
        eyebrow="Contact import"
        title={data.file_name || 'CSV import'}
        description={`Uploaded ${formatDateTime(data.created_at, timeZone)}`}
        actions={<ImportStatusBadge status={data.status} />}
      />

      <div className="flex max-w-3xl flex-col gap-6">
        <section aria-label="Progress" className="rounded-xl border border-line bg-card p-5">
          <ImportProgress job={data} estimatedRows={estimatedRows} />
        </section>

        {(data.status === 'completed' || data.status === 'failed') && <ImportResult job={data} timeZone={timeZone} />}

        {!importInProgress(data) && (
          <div className="flex flex-wrap gap-2">
            <Link to={`${base}/contacts`} className={buttonClasses('primary')}>
              View contacts
            </Link>
            {can('admin') && (
              <Link to={`${base}/contacts/imports/new`} className={buttonClasses('secondary')}>
                Import another file
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function ImportProgress({ job, estimatedRows }: { job: ContactImport; estimatedRows?: number }) {
  const running = importInProgress(job)
  const percent =
    job.status === 'completed'
      ? 100
      : estimatedRows && job.status === 'processing'
        ? Math.min(99, Math.round((job.total_rows / estimatedRows) * 100))
        : undefined

  const message =
    job.status === 'queued'
      ? 'Waiting to start…'
      : job.status === 'processing'
        ? `Importing… ${formatNumber(job.total_rows)}${estimatedRows ? ` of about ${formatNumber(estimatedRows)}` : ''} rows read`
        : job.status === 'completed'
          ? `Import complete. ${formatNumber(job.total_rows)} ${job.total_rows === 1 ? 'row' : 'rows'} read.`
          : 'The import stopped before it finished.'

  return (
    <div className="flex flex-col gap-3">
      <p aria-live="polite" className="text-sm text-ink">
        {message}
      </p>
      {job.status !== 'failed' && (
        <div
          role="progressbar"
          aria-label="Import progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="h-2 overflow-hidden rounded-full bg-paper-2"
        >
          <div
            className={running && percent === undefined ? 'h-full w-1/3 animate-pulse rounded-full bg-accent/60' : 'h-full rounded-full bg-accent transition-[width] duration-500'}
            style={percent !== undefined ? { width: `${percent}%` } : undefined}
          />
        </div>
      )}
      {running && <p className="text-[13px] text-muted">You can leave this page; the import keeps running.</p>}
    </div>
  )
}

function ImportResult({ job, timeZone }: { job: ContactImport; timeZone: string }) {
  const globalErrors = job.errors.filter((error) => error.row === null)
  const rowErrors = job.errors.filter((error) => error.row !== null)
  const listed = job.errors.length
  const problems = job.error_count + job.skipped_count

  const download = () => {
    const blob = new Blob([errorsToCsv(job.errors)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${(job.file_name || 'import').replace(/\.csv$/i, '')}-problems.csv`
    document.body.append(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  const stats = [
    { label: 'Created', value: job.created_count },
    { label: 'Updated', value: job.updated_count },
    { label: 'Skipped', value: job.skipped_count, hint: 'Opted out, so not opted in again' },
    { label: 'Errors', value: job.error_count, hint: 'Rows not imported' },
  ]

  return (
    <>
      {globalErrors.map((error, index) => (
        <div key={index} role="alert" className="flex items-start gap-2 rounded-lg border border-signal/25 bg-signal-soft/60 px-3 py-2.5 text-sm text-signal">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>{error.error}</span>
        </div>
      ))}

      <section aria-label="Result summary">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map((stat) => (
            <div key={stat.label} className="rounded-xl border border-line bg-card px-4 py-3">
              <dt className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{stat.label}</dt>
              <dd className="mt-1 font-display text-2xl font-semibold tracking-[-0.02em] text-ink">{formatNumber(stat.value)}</dd>
              {stat.hint && <dd className="text-[12px] text-muted">{stat.hint}</dd>}
            </div>
          ))}
        </dl>
        {job.finished_at && <p className="mt-2 text-[13px] text-muted">Finished {formatDateTime(job.finished_at, timeZone)}</p>}
      </section>

      {rowErrors.length > 0 && (
        <section aria-labelledby="import-problems" className="rounded-xl border border-line bg-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-2 px-5 py-3">
            <h2 id="import-problems" className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
              Rows that need attention
            </h2>
            <Button size="sm" variant="secondary" icon={<Download className="size-3.5" aria-hidden="true" />} onClick={download}>
              Download CSV
            </Button>
          </div>
          <div className="max-h-96 overflow-auto">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">Rows that need attention</caption>
              <thead>
                <tr className="border-b border-line-2 bg-paper/60 text-left font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
                  <th scope="col" className="w-20 px-5 py-2 font-normal">Line</th>
                  <th scope="col" className="px-5 py-2 font-normal">Problem</th>
                </tr>
              </thead>
              <tbody>
                {rowErrors.map((error, index) => (
                  <tr key={index} className="border-b border-line-2 last:border-b-0">
                    <td className="px-5 py-2 font-mono text-[13px] text-ink-2">{error.row}</td>
                    <td className="px-5 py-2 text-ink">{error.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {problems > listed && (
            <p className="border-t border-line-2 px-5 py-2.5 text-[13px] text-muted">
              Showing the first {formatNumber(listed)} of {formatNumber(problems)} problems.
            </p>
          )}
        </section>
      )}
    </>
  )
}
