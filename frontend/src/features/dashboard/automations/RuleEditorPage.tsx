import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Controller, FormProvider, useFieldArray, useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm, errorMessage, flattenDetails, isApiError } from '../../../api/errors'
import { Button, buttonClasses, EmptyState, Field, Input, PageHeader, PageSpinner, Select, Switch, useToast } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { ConfirmDialog } from '../campaigns/components/ConfirmDialog'
import { Notice } from '../campaigns/components/Notice'
import { RadioCards } from '../campaigns/components/RadioCards'
import {
  automationKeys,
  isFeatureGateError,
  nextPriority,
  triggerInfo,
  usePhoneNumbers,
  useRule,
  useRules,
  type AutomationRule,
  type AutomationTrigger,
} from './api'
import { ActionCard } from './components/ActionCard'
import { AutomationsNav } from './components/AutomationsNav'
import { KeywordChipsInput } from './components/KeywordChipsInput'
import { ShopActionsNotice } from './components/ShopActionsNotice'
import { emptyAction, formToBody, MAX_ACTIONS, MAX_KEYWORDS, ruleFieldMap, ruleSchema, ruleToForm, type RuleFormValues } from './ruleForm'

const triggers = Object.keys(triggerInfo) as AutomationTrigger[]

function Section({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  const id = `rule-section-${title.toLowerCase().replace(/\W+/g, '-')}`
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <div>
        <h2 id={id} className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
          {title}
        </h2>
        {description && <p className="text-sm text-muted">{description}</p>}
      </div>
      {children}
    </section>
  )
}

export function RuleEditorPage() {
  const { id } = useParams()
  const { workspaceId } = useWorkspace()
  const rule = useRule(workspaceId, id)

  if (id && rule.isPending) return <PageSpinner />
  if (id && rule.isError) {
    const missing = isApiError(rule.error) && rule.error.status === 404
    return (
      <EmptyState
        title={missing ? 'Rule not found' : "Couldn't load this rule"}
        description={missing ? 'It may have been deleted.' : errorMessage(rule.error)}
        action={
          <Link to={`/app/w/${workspaceId}/automations`} className={buttonClasses('secondary')}>
            Back to automations
          </Link>
        }
      />
    )
  }
  return <RuleEditor key={id ?? 'new'} rule={id ? (rule.data ?? null) : null} />
}

function RuleEditor({ rule }: { rule: AutomationRule | null }) {
  const { workspaceId, can } = useWorkspace()
  const readOnly = !can('admin')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const rules = useRules(workspaceId)
  const phones = usePhoneNumbers(workspaceId)
  const base = `/app/w/${workspaceId}/automations`

  const [initialValues] = useState(() => ruleToForm(rule))
  const form = useForm<RuleFormValues>({ resolver: zodResolver(ruleSchema), defaultValues: initialValues })
  const {
    control,
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = form
  const actions = useFieldArray({ control, name: 'actions' })
  const trigger = useWatch({ control, name: 'trigger' })
  const [upgrade, setUpgrade] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const onSubmit = handleSubmit(async (values) => {
    setUpgrade(false)
    const body = formToBody(values, rule?.priority ?? nextPriority(rules.data))
    try {
      const saved = rule
        ? await unwrap(api.PATCH('/api/v1/automations/rules/{id}/', { params: { path: { id: rule.id } }, body }))
        : await unwrap(api.POST('/api/v1/automations/rules/', { body }))
      queryClient.setQueryData(automationKeys.detail(workspaceId, saved.id), saved)
      void queryClient.invalidateQueries({ queryKey: automationKeys.lists(workspaceId) })
      toast({ title: rule ? 'Rule saved' : 'Rule created' })
      navigate(base)
    } catch (error) {
      if (isFeatureGateError(error)) {
        setUpgrade(true)
        return
      }
      const paths = isApiError(error, 'invalid') ? Object.keys(flattenDetails(error.details)) : []
      applyApiErrorToForm(error, setError, { fieldMap: ruleFieldMap(paths, values.actions) })
    }
  })

  async function remove() {
    if (!rule) return
    setDeleting(true)
    try {
      await unwrap(api.DELETE('/api/v1/automations/rules/{id}/', { params: { path: { id: rule.id } } }))
      queryClient.removeQueries({ queryKey: automationKeys.detail(workspaceId, rule.id) })
      void queryClient.invalidateQueries({ queryKey: automationKeys.lists(workspaceId) })
      toast({ title: 'Rule deleted' })
      navigate(base)
    } catch (error) {
      setConfirmDelete(false)
      setError('root.server', { message: errorMessage(error) })
    } finally {
      setDeleting(false)
    }
  }

  const actionsError = errors.actions?.root?.message ?? errors.actions?.message
  const title = rule ? rule.name : 'New rule'

  return (
    <FormProvider {...form}>
      <div className="flex flex-col gap-6">
        <PageHeader
          eyebrow={
            <Link to={base} className="hover:text-ink">
              Automations
            </Link>
          }
          title={title}
          description={rule ? `${triggerInfo[rule.trigger].label} rule` : 'Choose what starts the rule and what it does.'}
        />
        <AutomationsNav />

        <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex max-w-3xl flex-col gap-8">
          {readOnly && <Notice>You can view this rule. Only admins and owners can change automations.</Notice>}
          {upgrade && (
            <Notice
              tone="warning"
              title="Keyword automations aren't included in your plan"
              action={
                <Link to={`/app/w/${workspaceId}/billing`} className={buttonClasses('secondary', 'sm')}>
                  View plans
                </Link>
              }
            >
              Upgrade to reply automatically when customers send a keyword. Welcome and away messages keep working on your current plan.
            </Notice>
          )}
          {errors.root?.server?.message && <Notice tone="error">{errors.root.server.message}</Notice>}

          <fieldset disabled={readOnly} className="flex min-w-0 flex-col gap-8">
            <Section title="Basics">
              <Field label="Rule name" error={errors.name?.message} required>
                <Input {...register('name')} maxLength={120} placeholder="Price list reply" autoComplete="off" />
              </Field>
              <Controller
                control={control}
                name="is_active"
                render={({ field }) => (
                  <Switch checked={field.value} onCheckedChange={field.onChange} label="Active" description="Inactive rules never run." disabled={readOnly} />
                )}
              />
            </Section>

            <Section title="Trigger">
              <Controller
                control={control}
                name="trigger"
                render={({ field }) => (
                  <RadioCards
                    legend="Run this rule when"
                    value={field.value}
                    onChange={field.onChange}
                    disabled={readOnly}
                    options={triggers.map((value) => ({ value, label: triggerInfo[value].label, description: triggerInfo[value].description }))}
                  />
                )}
              />

              {trigger === 'keyword' && (
                <>
                  <Controller
                    control={control}
                    name="keywords"
                    render={({ field }) => (
                      <KeywordChipsInput
                        label="Keywords"
                        value={field.value}
                        onChange={field.onChange}
                        error={errors.keywords?.message}
                        hint={`Press Enter or type a comma after each keyword. Up to ${MAX_KEYWORDS}.`}
                        disabled={readOnly}
                        max={MAX_KEYWORDS}
                        required
                      />
                    )}
                  />
                  <Controller
                    control={control}
                    name="keyword_match"
                    render={({ field }) => (
                      <RadioCards
                        legend="Match"
                        value={field.value}
                        onChange={field.onChange}
                        disabled={readOnly}
                        options={[
                          { value: 'exact', label: 'Whole message', description: 'The message is just the keyword, like “price”.' },
                          { value: 'contains', label: 'Contains', description: 'The keyword appears anywhere, like “what is the price?”.' },
                        ]}
                      />
                    )}
                  />
                </>
              )}

              {trigger === 'outside_business_hours' && (
                <p className="text-sm text-muted">
                  Uses your{' '}
                  <Link to={`${base}/business-hours`} className="text-accent-2 underline underline-offset-4">
                    business hours
                  </Link>
                  . It doesn't run while business hours are turned off.
                </p>
              )}

              <Field label="Phone number" error={errors.phone_number_id?.message}>
                <Select
                  {...register('phone_number_id')}
                  options={[
                    { value: '', label: 'All numbers' },
                    ...(phones.data ?? []).map((phone) => ({ value: phone.id, label: `${phone.display_phone_number} · ${phone.verified_name}` })),
                  ]}
                />
              </Field>
            </Section>

            <Section title="Actions" description={`Run in order. Up to ${MAX_ACTIONS} actions.`}>
              <ol className="flex flex-col gap-3">
                {actions.fields.map((field, index) => (
                  <ActionCard
                    key={field.id}
                    index={index}
                    count={actions.fields.length}
                    onMove={(to) => actions.move(index, to)}
                    onRemove={() => actions.remove(index)}
                    readOnly={readOnly}
                  />
                ))}
              </ol>
              {actionsError && (
                <p role="alert" className="text-[13px] text-signal">
                  {actionsError}
                </p>
              )}
              {!readOnly && (
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    variant="secondary"
                    icon={<Plus className="size-4" aria-hidden="true" />}
                    onClick={() => actions.append(emptyAction())}
                    disabled={actions.fields.length >= MAX_ACTIONS}
                  >
                    Add action
                  </Button>
                  {actions.fields.length >= MAX_ACTIONS && <span className="text-[13px] text-muted">That's the maximum of {MAX_ACTIONS} actions.</span>}
                </div>
              )}
              <ShopActionsNotice />
              <Notice title="The 24-hour window">
                WhatsApp only delivers free-form messages, like Send text, within 24 hours of the customer's last message. Automations run
                when a customer writes, so replies normally fall inside that window. Send template works at any time.
              </Notice>
            </Section>

            <Section title="Limits">
              <Field
                label="Cooldown (minutes)"
                hint="Don't run this rule again for the same conversation within this time. 0 runs it every time."
                error={errors.cooldown_minutes?.message}
              >
                <Input type="number" min={0} step={1} inputMode="numeric" className="max-w-40" {...register('cooldown_minutes', { valueAsNumber: true })} />
              </Field>
              <Controller
                control={control}
                name="stop_processing"
                render={({ field }) => (
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    label="Stop other rules"
                    description="When this rule runs, rules below it are skipped for that message."
                    disabled={readOnly}
                  />
                )}
              />
            </Section>
          </fieldset>

          {!readOnly && (
            <div className="flex flex-col-reverse gap-2 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
              {rule ? (
                <Button variant="ghost" className="text-signal" onClick={() => setConfirmDelete(true)}>
                  Delete rule
                </Button>
              ) : (
                <span />
              )}
              <div className="flex flex-col-reverse gap-2 sm:flex-row">
                <Link to={base} className={buttonClasses('secondary')}>
                  Cancel
                </Link>
                <Button type="submit" loading={isSubmitting}>
                  {rule ? 'Save rule' : 'Create rule'}
                </Button>
              </div>
            </div>
          )}
        </form>

        <ConfirmDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title="Delete this rule?"
          description="It stops running straight away. Its past runs stay in the run log."
          confirmLabel="Delete rule"
          danger
          loading={deleting}
          onConfirm={() => void remove()}
        />
      </div>
    </FormProvider>
  )
}
