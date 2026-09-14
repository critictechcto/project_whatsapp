import { CircleAlert } from 'lucide-react'
import { fieldLabel, type FormIssue } from '../lib/formErrors'

type ErrorSummaryProps = {
  issues: readonly FormIssue[]
  /** Moves focus to the field; called when an issue is activated. */
  onSelect: (path: string) => void
}

/** Announced list of every problem, each linking to its field. */
export function ErrorSummary({ issues, onSelect }: ErrorSummaryProps) {
  if (!issues.length) return null
  return (
    <div role="alert" className="rounded-xl border border-signal/25 bg-signal-soft/50 p-4">
      <p className="flex items-center gap-2 text-sm font-medium text-signal">
        <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
        {issues.length === 1 ? 'Fix 1 problem before submitting' : `Fix ${issues.length} problems before submitting`}
      </p>
      <ul className="mt-2 space-y-1 pl-6 text-[13px]">
        {issues.map((issue) => (
          <li key={issue.path} className="list-disc text-ink-2 marker:text-signal">
            <button type="button" onClick={() => onSelect(issue.path)} className="text-left underline-offset-2 hover:underline">
              <span className="font-medium">{fieldLabel(issue.path)}:</span> {issue.message}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
