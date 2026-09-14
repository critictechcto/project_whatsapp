import { useQuery } from '@tanstack/react-query'
import { ArrowRight, CircleCheck, Circle } from 'lucide-react'
import { Link } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { workspaceKeys } from '../../../api/queryKeys'
import { PageHeader, Skeleton } from '../../../components/app'
import { cn } from '../../../lib/cn'
import { useWorkspace } from '../../../lib/workspace'
import { useMe } from '../auth/session'

const homeKeys = workspaceKeys('home')

type Step = {
  id: string
  title: string
  description: string
  to: string
  cta: string
  done: boolean | undefined
}

/** Workspace home: a setup checklist driven by real data (no placeholder numbers). */
export function HomePage() {
  const { workspaceId, workspace } = useWorkspace()
  const me = useMe()
  const firstName = me.data?.full_name?.split(' ')[0]

  const phones = useQuery({
    queryKey: homeKeys.custom(workspaceId, 'phone-numbers'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/whatsapp/phone-numbers/', { params: { query: { page_size: 1 } }, signal })),
  })
  const templates = useQuery({
    queryKey: homeKeys.custom(workspaceId, 'approved-templates'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/templates/', { params: { query: { status: 'APPROVED' } }, signal })),
  })
  const contacts = useQuery({
    queryKey: homeKeys.custom(workspaceId, 'contacts'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/contacts/', { params: { query: { page_size: 1 } }, signal })),
  })

  const hasResults = (query: { data?: { results: unknown[] }; isError: boolean }) =>
    query.data ? query.data.results.length > 0 : query.isError ? false : undefined

  const steps: Step[] = [
    {
      id: 'number',
      title: 'Connect your WhatsApp number',
      description: "Use Meta's Embedded Signup to link a number to the official WhatsApp Business Platform.",
      to: 'whatsapp',
      cta: 'Connect number',
      done: hasResults(phones),
    },
    {
      id: 'template',
      title: 'Get a message template approved',
      description: 'Business-initiated messages outside the 24-hour window need a template approved by Meta.',
      to: 'templates',
      cta: 'Open templates',
      done: hasResults(templates),
    },
    {
      id: 'contacts',
      title: 'Add contacts with opt-in',
      description: 'Import customers who agreed to hear from you on WhatsApp.',
      to: 'contacts',
      cta: 'Add contacts',
      done: hasResults(contacts),
    },
  ]

  const completed = steps.filter((step) => step.done).length
  const loading = steps.some((step) => step.done === undefined)

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow={workspace.name}
        title={firstName ? `Welcome, ${firstName}` : 'Welcome'}
        description="Finish these steps to start messaging customers on WhatsApp."
      />

      <section aria-labelledby="setup-heading" className="rounded-xl border border-line bg-card">
        <div className="flex items-center justify-between border-b border-line-2 px-5 py-3.5">
          <h2 id="setup-heading" className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
            Get set up
          </h2>
          {loading ? (
            <Skeleton className="h-4 w-20" />
          ) : (
            <p className="font-mono text-[12px] text-muted">
              {completed} of {steps.length} done
            </p>
          )}
        </div>
        <ol className="divide-y divide-line-2">
          {steps.map((step) => (
            <li key={step.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
              <span className="shrink-0">
                {step.done === undefined ? (
                  <Skeleton className="size-5 rounded-full" />
                ) : step.done ? (
                  <CircleCheck className="size-5 text-accent" aria-label="Done" />
                ) : (
                  <Circle className="size-5 text-line" aria-label="Not done" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p className={cn('text-sm font-medium', step.done ? 'text-muted' : 'text-ink')}>{step.title}</p>
                <p className="mt-0.5 text-[13px] text-muted">{step.description}</p>
              </div>
              <Link
                to={step.to}
                className="inline-flex items-center gap-1 text-sm font-medium text-accent-2 underline-offset-2 hover:underline"
              >
                {step.cta}
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
