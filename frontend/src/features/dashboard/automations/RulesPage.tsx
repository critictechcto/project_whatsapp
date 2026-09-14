import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Plus, Workflow } from 'lucide-react'
import { Link } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { errorMessage } from '../../../api/errors'
import { Button, buttonClasses, EmptyState, PageHeader, StatusBadge, Switch, Table, useToast, type Column } from '../../../components/app'
import { formatRelative } from '../../../lib/datetime'
import { formatNumber } from '../../../lib/format'
import { useWorkspace } from '../../../lib/workspace'
import { Notice } from '../campaigns/components/Notice'
import {
  actionLabels,
  automationKeys,
  isFeatureGateError,
  patchBody,
  rulesListKey,
  sortRules,
  triggerInfo,
  usePhoneNumbers,
  useRules,
  type AutomationRule,
} from './api'
import { AutomationsNav } from './components/AutomationsNav'

type Change = { rule: AutomationRule; patch: { is_active?: boolean; priority?: number } }

export function RulesPage() {
  const { workspaceId, can } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const rules = useRules(workspaceId)
  const phones = usePhoneNumbers(workspaceId)
  const canManage = can('admin')
  const base = `/app/w/${workspaceId}/automations`
  const listKey = rulesListKey(workspaceId)

  const update = useMutation({
    mutationFn: (changes: Change[]) =>
      Promise.all(
        changes.map(({ rule, patch }) =>
          unwrap(api.PATCH('/api/v1/automations/rules/{id}/', { params: { path: { id: rule.id } }, body: patchBody(rule, patch) })),
        ),
      ),
    onMutate: async (changes) => {
      await queryClient.cancelQueries({ queryKey: listKey })
      const previous = queryClient.getQueryData<AutomationRule[]>(listKey)
      queryClient.setQueryData<AutomationRule[]>(listKey, (current) =>
        current
          ? sortRules(
              current.map((rule) => {
                const change = changes.find((item) => item.rule.id === rule.id)
                return change ? { ...rule, ...change.patch } : rule
              }),
            )
          : current,
      )
      return { previous }
    },
    onError: (error, _changes, context) => {
      if (context?.previous) queryClient.setQueryData(listKey, context.previous)
      toast({
        title: "Couldn't update the rule",
        description: isFeatureGateError(error) ? "Keyword automations aren't included in your plan." : errorMessage(error),
      })
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: automationKeys.all(workspaceId) }),
  })

  function move(index: number, delta: -1 | 1) {
    const list = rules.data
    const target = index + delta
    if (!list || target < 0 || target >= list.length) return
    const ordered = [...list]
    ;[ordered[index], ordered[target]] = [ordered[target], ordered[index]]
    const changes = ordered
      .map((rule, position) => ({ rule, patch: { priority: position } }))
      .filter(({ rule, patch }) => rule.priority !== patch.priority)
    if (changes.length) update.mutate(changes)
  }

  const phoneLabel = (id: string | null | undefined) =>
    !id ? 'All numbers' : (phones.data?.find((phone) => phone.id === id)?.display_phone_number ?? 'Removed number')

  const list = rules.data ?? []

  const columns: Column<AutomationRule>[] = [
    ...(canManage
      ? [
          {
            id: 'order',
            header: <span className="sr-only">Order</span>,
            className: 'w-20',
            cell: (rule: AutomationRule) => {
              const index = list.indexOf(rule)
              return (
                <div className="flex gap-0.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Move “${rule.name}” up`}
                    icon={<ArrowUp className="size-4" aria-hidden="true" />}
                    disabled={index <= 0 || update.isPending}
                    onClick={() => move(index, -1)}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Move “${rule.name}” down`}
                    icon={<ArrowDown className="size-4" aria-hidden="true" />}
                    disabled={index === list.length - 1 || update.isPending}
                    onClick={() => move(index, 1)}
                  />
                </div>
              )
            },
          },
        ]
      : []),
    {
      id: 'name',
      header: 'Rule',
      cell: (rule) => (
        <div className="min-w-0">
          <Link to={`${base}/${rule.id}`} className="font-medium text-ink underline-offset-4 hover:underline">
            {rule.name}
          </Link>
          {rule.trigger === 'keyword' && rule.keywords?.length ? (
            <p className="truncate font-mono text-[12px] text-muted">
              {rule.keyword_match === 'contains' ? 'contains ' : ''}
              {rule.keywords.slice(0, 4).join(', ')}
              {rule.keywords.length > 4 ? ` +${rule.keywords.length - 4}` : ''}
            </p>
          ) : null}
          <p className="truncate text-[12px] text-muted">{rule.actions.map((action) => actionLabels[action.type]).join(' → ')}</p>
        </div>
      ),
    },
    { id: 'trigger', header: 'Trigger', cell: (rule) => <StatusBadge tone="blue">{triggerInfo[rule.trigger].label}</StatusBadge> },
    { id: 'scope', header: 'Number', hideOnMobile: true, cell: (rule) => <span className="text-[13px]">{phoneLabel(rule.phone_number_id)}</span> },
    { id: 'runs', header: 'Runs', align: 'right', hideOnMobile: true, cell: (rule) => <span className="font-mono">{formatNumber(rule.run_count)}</span> },
    {
      id: 'last',
      header: 'Last run',
      hideOnMobile: true,
      cell: (rule) => <span className="text-[13px] text-muted">{rule.last_triggered_at ? formatRelative(rule.last_triggered_at) : 'Never'}</span>,
    },
    {
      id: 'active',
      header: 'Active',
      cell: (rule) =>
        canManage ? (
          <Switch
            checked={rule.is_active}
            onCheckedChange={(checked) => update.mutate([{ rule, patch: { is_active: checked } }])}
            label={`Active: ${rule.name}`}
            hideLabel
          />
        ) : (
          <StatusBadge tone={rule.is_active ? 'green' : 'neutral'}>{rule.is_active ? 'Active' : 'Off'}</StatusBadge>
        ),
    },
  ]

  const newRule = canManage ? (
    <Link to={`${base}/new`} className={buttonClasses('primary')}>
      <Plus className="size-4" aria-hidden="true" />
      New rule
    </Link>
  ) : null

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Automations"
        description="Reply to keywords, welcome new contacts and send away messages without anyone at the keyboard."
        actions={newRule}
      />
      <AutomationsNav />

      <Notice>
        Rules run from top to bottom for each incoming message. Free-form replies only reach customers within 24 hours of their last message,
        which is when automations run.
      </Notice>

      {rules.isError ? (
        <Notice
          tone="error"
          title="Couldn't load rules"
          action={
            <Button variant="secondary" size="sm" onClick={() => void rules.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(rules.error)}
        </Notice>
      ) : (
        <Table
          caption="Automation rules, in the order they run"
          columns={columns}
          rows={list}
          getRowId={(rule) => rule.id}
          loading={rules.isPending}
          empty={
            <EmptyState
              icon={<Workflow className="size-5" aria-hidden="true" />}
              title="No rules yet"
              description="Start with an away message for when you're closed, or a reply to a common keyword like “price”."
              action={newRule}
            />
          }
        />
      )}
    </div>
  )
}
