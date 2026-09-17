import { useSearchParams } from 'react-router'
import { isApiError } from '../../../api/errors'
import { PageHeader, Tabs, type TabOption } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { isFeatureUnavailable, useCommerceReport, useOverview } from './api'
import { CommerceReport } from './components/CommerceReport'
import { KpiCards } from './components/KpiCards'
import { MessagesReport } from './components/MessagesReport'
import { RangeControl } from './components/RangeControl'
import { ReportError } from './components/ReportStates'
import { CampaignsReport, TeamReport, TemplatesReport } from './components/TableReports'
import { UpgradePanel } from './components/UpgradePanel'
import { formatRangeLabel, previousRange, rangeFromSearch, todayIn } from './range'
import type { DateRange } from './range'

type ReportTab = 'messages' | 'templates' | 'campaigns' | 'team' | 'commerce'

const tabLabels: Record<ReportTab, string> = {
  messages: 'Messages',
  templates: 'Templates',
  campaigns: 'Campaigns',
  team: 'Team',
  commerce: 'Commerce',
}

/** Workspace analytics: range in the URL (`?from=&to=`), KPIs vs the previous period, one tab per report. */
export function AnalyticsPage() {
  const { timeZone } = useWorkspace()
  const [search, setSearch] = useSearchParams()
  const today = todayIn(timeZone)
  const { range, invalid } = rangeFromSearch(search, today)

  const overview = useOverview(range)
  const locked = overview.isError && isFeatureUnavailable(overview.error, 'analytics')
  const commerce = useCommerceReport(range, !locked)
  // Hidden only once the API says commerce isn't available; while it loads the tab stays so the layout doesn't jump back.
  const commerceHidden = commerce.isError && isApiError(commerce.error) && commerce.error.status === 409

  const tabs: TabOption<ReportTab>[] = (Object.keys(tabLabels) as ReportTab[])
    .filter((tab) => tab !== 'commerce' || !commerceHidden)
    .map((tab) => ({ value: tab, label: tabLabels[tab] }))
  const requested = search.get('tab') as ReportTab | null
  const tab: ReportTab = requested && tabs.some((item) => item.value === requested) ? requested : 'messages'

  function update(changes: { range?: DateRange; tab?: ReportTab }) {
    setSearch(
      (current) => {
        const next = new URLSearchParams(current)
        if (changes.range) {
          next.set('from', changes.range.from)
          next.set('to', changes.range.to)
        }
        if (changes.tab) {
          if (changes.tab === 'messages') next.delete('tab')
          else next.set('tab', changes.tab)
        }
        return next
      },
      { replace: Boolean(changes.tab) },
    )
  }

  const previous = previousRange(range)

  if (locked) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Analytics" description="How your WhatsApp messages, campaigns, team and store are doing." />
        <UpgradePanel />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Analytics"
        description={
          <>
            <span className="text-ink">{formatRangeLabel(range)}</span>, compared with {formatRangeLabel(previous)}. Dates are in your
            workspace time zone.
          </>
        }
        actions={<RangeControl range={range} today={today} onChange={(next) => update({ range: next })} />}
      />

      {invalid && (
        <p role="status" className="rounded-lg border border-amber/25 bg-amber-soft/70 px-3.5 py-2.5 text-sm text-ink-2">
          The dates in this link aren&apos;t a valid range, so this shows the last 30 days.
        </p>
      )}

      {overview.isError ? (
        <ReportError title="Couldn't load the overview" error={overview.error} onRetry={() => void overview.refetch()} />
      ) : (
        <KpiCards overview={overview.data} loading={overview.isPending} />
      )}

      <Tabs<ReportTab> label="Reports" items={tabs} value={tab} onValueChange={(next) => update({ tab: next })}>
        {tab === 'messages' && <MessagesReport range={range} />}
        {tab === 'templates' && <TemplatesReport range={range} />}
        {tab === 'campaigns' && <CampaignsReport range={range} />}
        {tab === 'team' && <TeamReport range={range} />}
        {tab === 'commerce' && <CommerceReport range={range} query={commerce} />}
      </Tabs>
    </div>
  )
}
