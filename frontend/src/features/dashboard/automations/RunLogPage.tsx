import { useState } from 'react'
import { Link } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { errorMessage } from '../../../api/errors'
import { useCursorQuery } from '../../../api/pagination'
import { EmptyState, Field, PageHeader, Select, StatusBadge, Table, type Column } from '../../../components/app'
import { formatDateTime } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { Notice } from '../campaigns/components/Notice'
import { automationKeys, runStatusInfo, useRules, type AutomationRun, type RunStatus } from './api'
import { AutomationsNav } from './components/AutomationsNav'

const statuses = Object.keys(runStatusInfo) as RunStatus[]

export function RunLogPage() {
  const { workspaceId, timeZone } = useWorkspace()
  const [rule, setRule] = useState('')
  const [status, setStatus] = useState<RunStatus | ''>('')
  const rules = useRules(workspaceId)

  const runs = useCursorQuery<AutomationRun>({
    queryKey: automationKeys.custom(workspaceId, 'runs', { rule, status }),
    queryFn: ({ cursor, signal }) =>
      unwrap(
        api.GET('/api/v1/automations/runs/', {
          params: { query: { rule: rule || undefined, status: status || undefined, cursor } },
          signal,
        }),
      ),
  })

  const columns: Column<AutomationRun>[] = [
    { id: 'time', header: 'Time', cell: (run) => <span className="whitespace-nowrap text-[13px]">{formatDateTime(run.created_at, timeZone)}</span> },
    { id: 'rule', header: 'Rule', cell: (run) => <span className="font-medium text-ink">{run.rule.name}</span> },
    {
      id: 'status',
      header: 'Status',
      cell: (run) => <StatusBadge tone={runStatusInfo[run.status].tone}>{runStatusInfo[run.status].label}</StatusBadge>,
    },
    { id: 'detail', header: 'Detail', hideOnMobile: true, className: 'min-w-56', cell: (run) => <span className="text-[13px] text-ink-2">{run.detail || '—'}</span> },
    {
      id: 'conversation',
      header: <span className="sr-only">Conversation</span>,
      cell: (run) => (
        <Link to={`/app/w/${workspaceId}/inbox/${run.conversation_id}`} className="whitespace-nowrap text-[13px] text-accent-2 underline-offset-4 hover:underline">
          View conversation
        </Link>
      ),
    },
  ]

  const filtered = Boolean(rule || status)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Run log" description="Every time a rule ran, and what happened." />
      <AutomationsNav />

      <div className="grid gap-3 sm:max-w-xl sm:grid-cols-2">
        <Field label="Rule">
          <Select
            value={rule}
            onChange={(event) => setRule(event.target.value)}
            options={[{ value: '', label: 'All rules' }, ...(rules.data ?? []).map((item) => ({ value: item.id, label: item.name }))]}
          />
        </Field>
        <Field label="Status">
          <Select
            value={status}
            onChange={(event) => setStatus(event.target.value as RunStatus | '')}
            options={[{ value: '', label: 'Any status' }, ...statuses.map((value) => ({ value, label: runStatusInfo[value].label }))]}
          />
        </Field>
      </div>

      {runs.isError ? (
        <Notice tone="error" title="Couldn't load the run log">
          {errorMessage(runs.error)}
        </Notice>
      ) : (
        <Table
          caption="Automation runs, newest first"
          columns={columns}
          rows={runs.items}
          getRowId={(run) => run.id}
          loading={runs.isPending}
          hasNextPage={runs.hasNextPage}
          isFetchingNextPage={runs.isFetchingNextPage}
          onLoadMore={() => void runs.fetchNextPage()}
          empty={
            filtered ? (
              <EmptyState title="No runs match these filters" />
            ) : (
              <EmptyState title="No runs yet" description="Runs appear here once an active rule matches an incoming message." />
            )
          }
        />
      )}
    </div>
  )
}
