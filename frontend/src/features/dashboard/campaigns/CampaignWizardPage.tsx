import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { FormProvider, useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm, errorMessage, flattenDetails, isApiError } from '../../../api/errors'
import type { MessageTemplate } from '../../../api/types'
import { Button, buttonClasses, EmptyState, PageHeader, PageSpinner, templateKeys, useToast } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { campaignKeys, storeCampaign, useCampaign, type Campaign } from './api'
import { campaignError, type FriendlyError } from './campaignErrors'
import { Notice } from './components/Notice'
import { Stepper } from './components/Stepper'
import { isEditable } from './status'
import { normaliseMapping } from './variables'
import { AudienceStep } from './wizard/AudienceStep'
import { PersonaliseStep } from './wizard/PersonaliseStep'
import { ReviewStep } from './wizard/ReviewStep'
import { ScheduleStep } from './wizard/ScheduleStep'
import { TemplateStep } from './wizard/TemplateStep'
import { valuesFromCampaign, wizardSchema, wizardSteps, writeBody, type WizardValues } from './wizardSchema'

/** API error paths that differ from form paths. */
const apiFieldMap: Record<string, string> = { scheduled_at: 'schedule.at', consent_attested: 'consent' }

function stepIndexForPath(path: string): number {
  return wizardSteps.findIndex((step) => step.fields.some((field) => path === field || path.startsWith(`${field}.`)))
}

export function CampaignWizardPage() {
  const { id } = useParams()
  const { workspaceId } = useWorkspace()
  const campaign = useCampaign(workspaceId, id)
  const base = `/app/w/${workspaceId}/campaigns`

  if (id && campaign.isPending) return <PageSpinner />
  if (id && campaign.isError) {
    return (
      <EmptyState
        title="Couldn't open this campaign"
        description={errorMessage(campaign.error)}
        action={
          <Link to={base} className={buttonClasses('secondary')}>
            Back to campaigns
          </Link>
        }
      />
    )
  }
  if (campaign.data && !isEditable(campaign.data.status)) {
    return (
      <EmptyState
        title="This campaign can't be edited"
        description="It has already started, so its template, audience and schedule are fixed. Open the report to follow delivery or pause it."
        action={
          <Link to={`${base}/${campaign.data.id}`} className={buttonClasses('secondary')}>
            View report
          </Link>
        }
      />
    )
  }
  return <CampaignWizard key={id ?? 'new'} campaign={id ? (campaign.data ?? null) : null} />
}

function CampaignWizard({ campaign }: { campaign: Campaign | null }) {
  const { workspaceId } = useWorkspace()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [searchParams] = useSearchParams()
  const campaignId = campaign?.id
  const base = `/app/w/${workspaceId}/campaigns`

  const [initialValues] = useState(() => valuesFromCampaign(campaign))
  const form = useForm<WizardValues>({ resolver: zodResolver(wizardSchema), defaultValues: initialValues, mode: 'onTouched' })
  const { trigger, getValues, setValue, setError, clearErrors, control } = form
  const scheduleMode = useWatch({ control, name: 'schedule.mode' })
  const lastSaved = useRef(campaign ? JSON.stringify(writeBody(initialValues)) : '')
  const headingRef = useRef<HTMLHeadingElement>(null)
  const firstRender = useRef(true)
  const [busy, setBusy] = useState<'save' | 'launch' | null>(null)
  const [alert, setAlert] = useState<FriendlyError | null>(null)

  const requested = wizardSteps.findIndex((step) => step.id === searchParams.get('step'))
  const current = campaignId && requested > 0 ? requested : 0
  const step = wizardSteps[current]

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    headingRef.current?.focus()
  }, [current])

  function showStep(index: number, id: string | undefined = campaignId) {
    if (!id) return
    navigate(`${base}/${id}/edit?step=${wizardSteps[index].id}`, { replace: !campaignId })
  }

  /** Shapes the variable mapping to the chosen template's placeholders. */
  function syncMapping() {
    const templateId = getValues('template_id')
    const template = templateId ? queryClient.getQueryData<MessageTemplate>(templateKeys.detail(workspaceId, templateId)) : undefined
    if (!template) return
    const currentMapping = getValues('variable_mapping')
    const next = normaliseMapping(template, currentMapping)
    if (JSON.stringify(next) !== JSON.stringify(currentMapping)) setValue('variable_mapping', next)
  }

  function showError(error: unknown) {
    if (isApiError(error, 'invalid')) {
      const paths = Object.keys(flattenDetails(error.details)).map((path) => apiFieldMap[path] ?? path)
      const known = paths.filter((path) => stepIndexForPath(path) >= 0)
      applyApiErrorToForm(error, setError, { fieldMap: apiFieldMap, fields: known })
      const first = Math.min(...known.map(stepIndexForPath))
      if (Number.isFinite(first) && first !== current) showStep(first)
      return
    }
    setAlert(campaignError(error))
    if (campaignId && isApiError(error, 'campaign_not_editable')) {
      void queryClient.invalidateQueries({ queryKey: campaignKeys.detail(workspaceId, campaignId) })
    }
  }

  /** Creates or updates the draft. Returns its id, or null when saving failed. */
  async function save(): Promise<string | null> {
    syncMapping()
    const body = writeBody(getValues())
    const json = JSON.stringify(body)
    if (campaignId && json === lastSaved.current) return campaignId
    setBusy('save')
    try {
      const saved = campaignId
        ? await unwrap(api.PATCH('/api/v1/campaigns/{id}/', { params: { path: { id: campaignId } }, body }))
        : await unwrap(api.POST('/api/v1/campaigns/', { body }))
      lastSaved.current = json
      storeCampaign(queryClient, workspaceId, saved)
      void queryClient.invalidateQueries({ queryKey: campaignKeys.lists(workspaceId) })
      return saved.id
    } catch (error) {
      showError(error)
      return null
    } finally {
      setBusy(null)
    }
  }

  async function goTo(target: number) {
    if (target === current || busy) return
    setAlert(null)
    clearErrors('root')
    syncMapping()

    if (target < current) {
      const valid = await trigger([...step.fields])
      if (!valid) {
        clearErrors()
        showStep(target)
        return
      }
      const id = await save()
      if (id) showStep(target, id)
      return
    }

    if (!(await trigger([...step.fields]))) return
    const id = await save()
    if (!id) return
    for (let index = current + 1; index < target; index += 1) {
      if (!(await trigger([...wizardSteps[index].fields]))) {
        showStep(index, id)
        return
      }
    }
    showStep(target, id)
  }

  async function launch() {
    if (!campaignId || busy) return
    setAlert(null)
    clearErrors('root')
    syncMapping()

    const result = wizardSchema.safeParse(getValues())
    if (!result.success) {
      await trigger()
      const first = Math.min(...result.error.issues.map((issue) => stepIndexForPath(issue.path.map(String).join('.'))).filter((index) => index >= 0))
      if (Number.isFinite(first) && first !== current) showStep(first)
      return
    }

    const id = await save()
    if (!id) return
    setBusy('launch')
    try {
      const { schedule } = result.data
      const launched = await unwrap(
        api.POST('/api/v1/campaigns/{id}/launch/', {
          params: { path: { id } },
          body: { consent_attested: true, scheduled_at: schedule.mode === 'later' ? schedule.at : null },
        }),
      )
      navigate(`${base}/${launched.id}`)
      storeCampaign(queryClient, workspaceId, launched)
      void queryClient.invalidateQueries({ queryKey: campaignKeys.lists(workspaceId) })
      toast({
        title: launched.status === 'scheduled' ? 'Campaign scheduled' : 'Campaign launched',
        description: launched.status === 'scheduled' ? 'It starts sending at the time you chose.' : 'Delivery updates appear on this page as Meta reports them.',
      })
    } catch (error) {
      showError(error)
      setBusy(null)
    }
  }

  const rootError = form.formState.errors.root?.server?.message
  const isReview = step.id === 'review'

  return (
    <FormProvider {...form}>
      <div className="flex flex-col gap-6">
        <PageHeader
          eyebrow={
            <Link to={base} className="hover:text-ink">
              Campaigns
            </Link>
          }
          title={campaign ? 'Edit campaign' : 'New campaign'}
          description={campaign ? `“${campaign.name}” is saved as a ${campaign.status} each time you change steps.` : 'Your draft is saved each time you move to another step.'}
        />

        <Stepper label="Campaign steps" steps={wizardSteps} current={current} onSelect={(index) => void goTo(index)} disabled={busy !== null} />

        <form
          noValidate
          aria-labelledby="wizard-step-title"
          className="rounded-xl border border-line bg-card p-4 sm:p-6"
          onSubmit={(event) => {
            event.preventDefault()
            void (isReview ? launch() : goTo(current + 1))
          }}
        >
          <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
            Step {current + 1} of {wizardSteps.length}
          </p>
          <h2 id="wizard-step-title" ref={headingRef} tabIndex={-1} className="mt-1 font-display text-xl font-semibold tracking-[-0.01em] text-ink outline-none">
            {step.title}
          </h2>

          {(alert || rootError) && (
            <Notice
              tone="error"
              className="mt-4"
              action={
                alert?.billing ? (
                  <Link to={`/app/w/${workspaceId}/billing`} className={buttonClasses('secondary', 'sm')}>
                    View plans
                  </Link>
                ) : undefined
              }
            >
              {alert?.message ?? rootError}
            </Notice>
          )}

          <div className="mt-5">
            {step.id === 'template' && <TemplateStep />}
            {step.id === 'audience' && <AudienceStep campaignId={campaignId} />}
            {step.id === 'personalise' && <PersonaliseStep />}
            {step.id === 'schedule' && <ScheduleStep />}
            {step.id === 'review' && <ReviewStep campaignId={campaignId} />}
          </div>

          <div className="mt-6 flex flex-col-reverse gap-2 border-t border-line-2 pt-4 sm:flex-row sm:items-center sm:justify-between">
            {current > 0 ? (
              <Button variant="secondary" icon={<ArrowLeft className="size-4" aria-hidden="true" />} onClick={() => void goTo(current - 1)} disabled={busy !== null}>
                Back
              </Button>
            ) : (
              <Link to={base} className={buttonClasses('ghost')}>
                Cancel
              </Link>
            )}
            {isReview ? (
              <Button type="submit" loading={busy === 'launch'} disabled={busy === 'save'}>
                {scheduleMode === 'later' ? 'Schedule campaign' : 'Launch campaign'}
              </Button>
            ) : (
              <Button type="submit" loading={busy === 'save'}>
                Save and continue
              </Button>
            )}
          </div>
        </form>
      </div>
    </FormProvider>
  )
}
