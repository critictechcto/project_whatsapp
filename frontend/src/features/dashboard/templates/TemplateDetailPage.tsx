import { Copy, FileText, Megaphone, Pencil, Send, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { errorMessage, isApiError } from '../../../api/errors'
import type { MessageTemplate } from '../../../api/types'
import {
  Button,
  buttonClasses,
  Dialog,
  EmptyState,
  PageHeader,
  PageSpinner,
  StatusBadge,
  useToast,
  WhatsAppMessagePreview,
} from '../../../components/app'
import { formatDateTime } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { FormAlert } from './components/FormAlert'
import { useDeleteTemplate, useSubmitTemplate, useTemplate } from './api'
import { CategoryBadge, QualityBadge, RejectionNotice } from './components/TemplateBadges'
import { previewFromTemplate } from './lib/builderModel'
import { categoryLabels, EDITABLE_STATUSES, languageLabel, qualityExplanations, statusExplanations } from './lib/constants'

export function TemplateDetailPage() {
  const { id = '' } = useParams()
  const { workspaceId } = useWorkspace()
  const template = useTemplate(id, { pollWhilePending: true })
  const templatesPath = `/app/w/${workspaceId}/templates`

  if (template.isPending) return <PageSpinner label="Loading template" />
  if (template.isError) {
    const missing = isApiError(template.error) && template.error.status === 404
    return (
      <EmptyState
        icon={<FileText />}
        title={missing ? 'Template not found' : "Couldn't load this template"}
        description={missing ? 'It may have been deleted or belong to another workspace.' : errorMessage(template.error)}
        action={
          missing ? (
            <Link to={templatesPath} className={buttonClasses('secondary')}>
              Back to templates
            </Link>
          ) : (
            <Button variant="secondary" onClick={() => void template.refetch()}>
              Try again
            </Button>
          )
        }
      />
    )
  }
  return <TemplateDetail template={template.data} />
}

function Detail({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-4">
      <dt className="text-[13px] text-muted">{term}</dt>
      <dd className="min-w-0 text-sm text-ink">{children}</dd>
    </div>
  )
}

function TemplateDetail({ template }: { template: MessageTemplate }) {
  const { workspaceId, timeZone, can } = useWorkspace()
  const navigate = useNavigate()
  const { toast } = useToast()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const remove = useDeleteTemplate()
  const submit = useSubmitTemplate(template.id)
  const templatesPath = `/app/w/${workspaceId}/templates`
  const canManage = can('admin')
  const editable = EDITABLE_STATUSES.includes(template.status)
  const submittedToMeta = Boolean(template.meta_template_id)

  const onDelete = () =>
    remove.mutate(template.id, {
      onSuccess: () => {
        setConfirmDelete(false)
        toast({ tone: 'success', title: `Deleted ${template.name}` })
        navigate(templatesPath, { replace: true })
      },
    })

  const history = [
    { label: 'Created in UpChatz', at: template.created_at },
    { label: 'Submitted to Meta', at: template.submitted_at },
    { label: 'Last synced with Meta', at: template.last_synced_at },
  ].filter((entry): entry is { label: string; at: string } => Boolean(entry.at))

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={templatesPath} className="hover:text-ink">
            Templates
          </Link>
        }
        title={<span className="break-all font-mono text-[1.35rem]">{template.name}</span>}
        description={`${categoryLabels[template.category]} template in ${languageLabel(template.language)}`}
        actions={
          <>
            {template.status === 'APPROVED' && (
              <Link to={`/app/w/${workspaceId}/campaigns/new?template=${template.id}`} className={buttonClasses('primary')}>
                <Megaphone className="size-4" aria-hidden="true" />
                Use in campaign
              </Link>
            )}
            {canManage && editable && (
              <>
                <Button variant={template.status === 'DRAFT' ? 'primary' : 'secondary'} loading={submit.isPending} icon={<Send className="size-4" aria-hidden="true" />} onClick={() => submit.mutate()}>
                  Submit for review
                </Button>
                <Link to="edit" className={buttonClasses('secondary')}>
                  <Pencil className="size-4" aria-hidden="true" />
                  Edit
                </Link>
              </>
            )}
            {canManage && (
              <>
                <Link to={`${templatesPath}/new?from=${template.id}`} className={buttonClasses('secondary')}>
                  <Copy className="size-4" aria-hidden="true" />
                  Duplicate
                </Link>
                <Button variant="ghost" icon={<Trash2 className="size-4" aria-hidden="true" />} onClick={() => setConfirmDelete(true)}>
                  Delete
                </Button>
              </>
            )}
          </>
        }
      />

      {submit.isError && <FormAlert message={`Couldn't submit to Meta: ${errorMessage(submit.error)}`} />}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
        <div className="flex min-w-0 flex-col gap-5">
          <section aria-labelledby="template-status" className="rounded-xl border border-line bg-card p-5">
            <div className="flex flex-wrap items-center gap-3">
              <h2 id="template-status" className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
                Status
              </h2>
              <StatusBadge status={template.status} />
            </div>
            <p className="mt-2 text-sm text-ink-2" aria-live="polite">
              {statusExplanations[template.status] ?? 'Status reported by Meta.'}
            </p>
            {template.status === 'REJECTED' && <RejectionNotice reason={template.rejected_reason} className="mt-4" />}
          </section>

          <section aria-labelledby="template-details" className="rounded-xl border border-line bg-card px-5 pt-4">
            <h2 id="template-details" className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
              Details
            </h2>
            <dl className="mt-1 divide-y divide-line-2">
              <Detail term="Category">
                <CategoryBadge category={template.category} />
                {template.previous_category && template.previous_category !== template.category && (
                  <p className="mt-1.5 text-[13px] text-muted">
                    Meta changed the category from {categoryLabels[template.previous_category]} to {categoryLabels[template.category]}.
                  </p>
                )}
              </Detail>
              <Detail term="Language">
                {languageLabel(template.language)} <span className="font-mono text-[12px] text-muted">({template.language})</span>
              </Detail>
              <Detail term="Quality">
                <QualityBadge score={template.quality_score} />
                <p className="mt-1.5 text-[13px] text-muted">{qualityExplanations[template.quality_score] ?? qualityExplanations.UNKNOWN}</p>
              </Detail>
              {submittedToMeta && (
                <Detail term="Meta template ID">
                  <span className="break-all font-mono text-[13px]">{template.meta_template_id}</span>
                </Detail>
              )}
              <Detail term="History">
                <ol className="flex flex-col gap-1.5">
                  {history.map((entry) => (
                    <li key={entry.label} className="flex flex-wrap gap-x-2">
                      <span>{entry.label}</span>
                      <time dateTime={entry.at} className="text-muted">
                        {formatDateTime(entry.at, timeZone)}
                      </time>
                    </li>
                  ))}
                </ol>
                <p className="mt-2 text-[12.5px] text-muted">Meta doesn&apos;t share a full review history; UpChatz shows the latest status it reports.</p>
              </Detail>
            </dl>
          </section>
        </div>

        <aside aria-label="Preview" className="flex flex-col gap-2 lg:sticky lg:top-6">
          <h2 className="font-display text-base font-semibold tracking-[-0.01em] text-ink">Preview</h2>
          <WhatsAppMessagePreview message={previewFromTemplate(template)} time="10:24 AM" />
          <p className="text-[12.5px] text-muted">Shown with the example values submitted to Meta.</p>
          {template.status !== 'APPROVED' && (
            <p className="text-[12.5px] text-muted">Only approved templates can be used in campaigns.</p>
          )}
        </aside>
      </div>

      <Dialog
        open={confirmDelete}
        onOpenChange={(open) => !remove.isPending && setConfirmDelete(open)}
        dismissible={!remove.isPending}
        title={`Delete ${template.name}?`}
        description="This can't be undone."
        footer={
          <>
            <Button variant="ghost" disabled={remove.isPending} onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={onDelete}>
              Delete template
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3 text-sm text-ink-2">
          {submittedToMeta ? (
            <>
              <p>The template is also deleted at Meta. Campaigns and automations that use it will stop sending it.</p>
              <p>
                Under Meta&apos;s current rules, you can&apos;t create a new template named <span className="font-mono">{template.name}</span> for 30 days
                after deleting it.
              </p>
            </>
          ) : (
            <p>This draft was never submitted to Meta, so only the copy in UpChatz is removed.</p>
          )}
          {remove.isError && <FormAlert message={errorMessage(remove.error)} />}
        </div>
      </Dialog>
    </div>
  )
}
