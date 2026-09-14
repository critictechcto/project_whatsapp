import { zodResolver } from '@hookform/resolvers/zod'
import { FileText, Smartphone } from 'lucide-react'
import { useId, useRef, type ReactNode } from 'react'
import { FormProvider, useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { errorMessage, isApiError } from '../../../api/errors'
import type { MessageTemplate } from '../../../api/types'
import {
  Button,
  buttonClasses,
  Checkbox,
  EmptyState,
  Field,
  Input,
  PageHeader,
  PageSpinner,
  Select,
  Textarea,
  useToast,
  WhatsAppMessagePreview,
} from '../../../components/app'
import { cn } from '../../../lib/cn'
import { useWorkspace } from '../../../lib/workspace'
import { FormAlert } from './components/FormAlert'
import { useSaveAndSubmitTemplate, useTemplate, useWhatsAppAccounts } from './api'
import { ButtonsEditor } from './components/ButtonsEditor'
import { ErrorSummary } from './components/ErrorSummary'
import { builderSchema } from './lib/builderSchema'
import {
  defaultBuilderValues,
  distinctVariables,
  formatTemplateName,
  fromTemplate,
  nextVariable,
  previewFromValues,
  toTemplateRequest,
  type BuilderValues,
  type HeaderType,
} from './lib/builderModel'
import { categoryOptions, EDITABLE_STATUSES, languageOptions } from './lib/constants'
import { applyTemplateApiError } from './lib/errorPaths'
import { errorAt, orderedIssues } from './lib/formErrors'
import { BODY_MAX_LENGTH, FOOTER_MAX_LENGTH, HEADER_TEXT_MAX_LENGTH, textLength, variableNumbers } from './lib/validate'

type Account = { id: string; name: string; waba_id: string }

/** `templates/new` (optionally `?from=<id>` to duplicate) and `templates/:id/edit`. */
export function TemplateBuilderPage() {
  const { workspaceId } = useWorkspace()
  const { id } = useParams()
  const [params] = useSearchParams()
  const fromId = id ? undefined : (params.get('from') ?? undefined)
  const source = useTemplate(id ?? fromId)
  const accounts = useWhatsAppAccounts()
  const templatesPath = `/app/w/${workspaceId}/templates`

  if ((id || fromId) && source.isPending) return <PageSpinner label="Loading template" />
  if (accounts.isPending) return <PageSpinner label="Loading WhatsApp accounts" />

  if (source.isError) {
    return (
      <EmptyState
        icon={<FileText />}
        title="Template not found"
        description="It may have been deleted."
        action={
          <Link to={templatesPath} className={buttonClasses('secondary')}>
            Back to templates
          </Link>
        }
      />
    )
  }

  if (id && source.data && !EDITABLE_STATUSES.includes(source.data.status)) {
    return (
      <EmptyState
        icon={<FileText />}
        title="This template can't be edited"
        description="Only draft or rejected templates can be changed. Duplicate it to create a new version."
        action={
          <Link to={`${templatesPath}/new?from=${id}`} className={buttonClasses('secondary')}>
            Duplicate template
          </Link>
        }
      />
    )
  }

  if (accounts.isError || !accounts.data?.results.length) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="New template" eyebrow={<Link to={templatesPath}>Templates</Link>} />
        <EmptyState
          icon={<Smartphone />}
          title={accounts.isError ? "Couldn't load your WhatsApp accounts" : 'Connect WhatsApp first'}
          description={
            accounts.isError
              ? errorMessage(accounts.error)
              : 'Templates belong to a WhatsApp Business Account. Connect your number with Meta Embedded Signup, then create templates.'
          }
          action={
            accounts.isError ? (
              <Button variant="secondary" onClick={() => void accounts.refetch()}>
                Try again
              </Button>
            ) : (
              <Link to={`/app/w/${workspaceId}/whatsapp`} className={buttonClasses('primary')}>
                Connect WhatsApp
              </Link>
            )
          }
        />
      </div>
    )
  }

  const accountList: Account[] = accounts.data.results.map((account) => ({ id: account.id, name: account.name, waba_id: account.waba_id }))
  const initial: BuilderValues = source.data
    ? { ...fromTemplate(source.data), ...(fromId ? { name: `${source.data.name}_copy`.slice(0, 512) } : {}) }
    : { ...defaultBuilderValues, waba: accountList[0].id }

  return <BuilderForm key={id ?? fromId ?? 'new'} initial={initial} accounts={accountList} editing={id ? source.data : undefined} />
}

function Section({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="rounded-xl border border-line bg-card p-5">
      <h2 id={headingId} className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
        {title}
      </h2>
      {description && <p className="mt-1 text-[13px] text-muted">{description}</p>}
      <div className="mt-4 flex flex-col gap-4">{children}</div>
    </section>
  )
}

const headerOptions: { value: HeaderType; label: string }[] = [
  { value: 'NONE', label: 'None' },
  { value: 'TEXT', label: 'Text' },
  { value: 'IMAGE', label: 'Image' },
  { value: 'VIDEO', label: 'Video' },
  { value: 'DOCUMENT', label: 'Document' },
  { value: 'LOCATION', label: 'Location' },
]

function Counter({ value, max }: { value: string; max: number }) {
  const length = textLength(value)
  return <span className={length > max ? 'text-signal' : undefined}>{`${length}/${max}`}</span>
}

type BuilderFormProps = { initial: BuilderValues; accounts: Account[]; editing?: MessageTemplate }

function BuilderForm({ initial, accounts, editing }: BuilderFormProps) {
  const { workspaceId } = useWorkspace()
  const navigate = useNavigate()
  const { toast } = useToast()
  const save = useSaveAndSubmitTemplate(editing?.id)
  const categoryId = useId()
  const otpId = useId()
  const bodyRef = useRef<HTMLTextAreaElement | null>(null)
  const headerRef = useRef<HTMLInputElement | null>(null)

  const form = useForm<BuilderValues>({ resolver: zodResolver(builderSchema), defaultValues: initial })
  const {
    control,
    register,
    handleSubmit,
    setValue,
    getValues,
    setError,
    setFocus,
    formState: { errors, isSubmitted, isSubmitting },
  } = form
  const values = { ...defaultBuilderValues, ...useWatch({ control }) } as BuilderValues

  const submitted = Boolean(editing?.meta_template_id)
  const isAuth = values.category === 'AUTHENTICATION'
  const selectedCategory = categoryOptions.find((option) => option.value === values.category)
  const bodyVariables = distinctVariables(values.bodyText)
  const headerHasVariable = variableNumbers(values.headerText).length > 0
  const templatesPath = `/app/w/${workspaceId}/templates`

  const nameField = register('name')
  const bodyField = register('bodyText')
  const headerField = register('headerText')

  /** Keeps `bodyExamples` dense so every rendered example input has a string value. */
  const padExamples = (text: string) => {
    const needed = Math.max(0, ...variableNumbers(text))
    const current = getValues('bodyExamples')
    if (current.length < needed) setValue('bodyExamples', Array.from({ length: needed }, (_, i) => current[i] ?? ''))
  }

  const insertAtCursor = (field: 'bodyText' | 'headerText', element: HTMLTextAreaElement | HTMLInputElement | null, token: string) => {
    const current = getValues(field)
    const start = element?.selectionStart ?? current.length
    const end = element?.selectionEnd ?? current.length
    const next = `${current.slice(0, start)}${token}${current.slice(end)}`
    setValue(field, next, { shouldDirty: true, shouldValidate: isSubmitted })
    if (field === 'bodyText') padExamples(next)
    requestAnimationFrame(() => {
      element?.focus()
      element?.setSelectionRange(start + token.length, start + token.length)
    })
  }

  const onSubmit = handleSubmit(async (formValues) => {
    const body = toTemplateRequest(formValues)
    try {
      const { template, submitError } = await save.mutateAsync(body)
      if (submitError) {
        toast({
          tone: 'error',
          title: 'Saved as a draft, but not submitted',
          description: isApiError(submitError, 'invalid') ? errorMessage(submitError, 'Meta did not accept the template.') : errorMessage(submitError),
        })
      } else {
        toast({ tone: 'success', title: 'Submitted to Meta for review', description: 'Reviews often finish within minutes but can take up to 24 hours.' })
      }
      navigate(`${templatesPath}/${template.id}`)
    } catch (error) {
      applyTemplateApiError(error, setError, formValues, body)
    }
  })

  const issues = isSubmitted ? orderedIssues(errors) : []

  return (
    <FormProvider {...form}>
      <div className="flex flex-col gap-6">
        <PageHeader
          eyebrow={
            <Link to={templatesPath} className="hover:text-ink">
              Templates
            </Link>
          }
          title={editing ? `Edit ${editing.name}` : 'New template'}
          description="Build the message, check the preview, then submit it to Meta. Meta reviews every template before it can be sent."
        />

        <form onSubmit={onSubmit} noValidate className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
          <div className="flex min-w-0 flex-col gap-5">
            <Section title="Basics">
              {accounts.length > 1 && (
                <Field label="WhatsApp Business Account" required error={errors.waba?.message}>
                  <Select
                    disabled={submitted}
                    options={accounts.map((account) => ({ value: account.id, label: `${account.name} (${account.waba_id})` }))}
                    {...register('waba')}
                  />
                </Field>
              )}
              {accounts.length === 1 && errors.waba?.message && <FormAlert message={errors.waba.message} />}

              <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_12rem]">
                <Field
                  label="Name"
                  required
                  hint={submitted ? "Meta doesn't allow renaming a submitted template." : 'Lowercase letters, numbers and underscores. Spaces become underscores.'}
                  error={errors.name?.message}
                >
                  <Input
                    {...nameField}
                    disabled={submitted}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="order_update"
                    className="font-mono"
                    onChange={(event) => {
                      event.target.value = formatTemplateName(event.target.value)
                      void nameField.onChange(event)
                    }}
                  />
                </Field>
                <Field label="Language" required error={errors.language?.message}>
                  <Select disabled={submitted} options={languageOptions.map((o) => ({ value: o.value, label: `${o.label} (${o.value})` }))} {...register('language')} />
                </Field>
              </div>

              <fieldset aria-describedby={`${categoryId}-pricing`}>
                <legend className="text-[13px] font-medium text-ink">
                  Category
                  <span aria-hidden="true" className="ml-0.5 text-signal">
                    *
                  </span>
                </legend>
                <div className="mt-1.5 grid gap-2 md:grid-cols-3">
                  {categoryOptions.map((option) => {
                    const selected = values.category === option.value
                    return (
                      <label
                        key={option.value}
                        className={cn(
                          'flex cursor-pointer gap-2.5 rounded-lg border p-3 text-sm transition-colors',
                          selected ? 'border-accent bg-accent-soft/40' : 'border-line bg-card hover:border-ink/30',
                        )}
                      >
                        <input
                          type="radio"
                          value={option.value}
                          className="mt-0.5 size-4 shrink-0 accent-accent"
                          aria-describedby={`${categoryId}-${option.value}`}
                          {...register('category')}
                        />
                        <span className="min-w-0">
                          <span className="block font-medium text-ink">{option.label}</span>
                          <span id={`${categoryId}-${option.value}`} className="mt-0.5 block text-[12.5px] leading-snug text-muted">
                            {option.summary}
                          </span>
                        </span>
                      </label>
                    )
                  })}
                </div>
                <p id={`${categoryId}-pricing`} className="mt-2 text-[13px] text-muted">
                  {selectedCategory?.pricing} Meta may change the category during review if the content doesn&apos;t match.
                </p>
                {errors.category?.message && <p className="mt-1 text-[13px] text-signal">{errors.category.message}</p>}
              </fieldset>
            </Section>

            {isAuth ? (
              <Section
                title="Authentication message"
                description="Meta supplies the wording of authentication templates, so you can't add your own text, links or media. You choose the extras below."
              >
                <Checkbox
                  label="Add a security note"
                  description="Appends “For your security, do not share this code.”"
                  {...register('addSecurityRecommendation')}
                />
                <Field
                  label="Code expires after (minutes)"
                  hint="Optional. Shown in the footer. 1 to 90 minutes."
                  error={errorAt(errors, 'codeExpirationMinutes')}
                  className="max-w-xs"
                >
                  <Input inputMode="numeric" placeholder="10" {...register('codeExpirationMinutes')} />
                </Field>
                <fieldset>
                  <legend className="text-[13px] font-medium text-ink">Code button</legend>
                  <div className="mt-1.5 flex flex-col gap-2 sm:flex-row sm:gap-6">
                    <label className="flex items-center gap-2 text-sm text-ink">
                      <input type="radio" value="COPY_CODE" className="size-4 accent-accent" {...register('otpType')} />
                      Copy code
                    </label>
                    <label className="flex items-center gap-2 text-sm text-ink">
                      <input type="radio" value="ONE_TAP" className="size-4 accent-accent" aria-describedby={`${otpId}-one-tap`} {...register('otpType')} />
                      One-tap autofill (Android app)
                    </label>
                  </div>
                  <p id={`${otpId}-one-tap`} className="mt-1 text-[13px] text-muted">
                    One-tap autofill needs your Android app&apos;s package name and signature hash; other devices get a copy button.
                  </p>
                  {errorAt(errors, 'otpType') && <p className="mt-1 text-[13px] text-signal">{errorAt(errors, 'otpType')}</p>}
                </fieldset>
                <Field label="Button text" hint={<Counter value={values.otpButtonText} max={25} />} error={errorAt(errors, 'otpButtonText')}>
                  <Input placeholder="Copy code" {...register('otpButtonText')} />
                </Field>
                {values.otpType === 'ONE_TAP' && (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Package name" required error={errorAt(errors, 'packageName')}>
                      <Input placeholder="in.sharmasweets.app" className="font-mono" {...register('packageName')} />
                    </Field>
                    <Field label="Signature hash" required error={errorAt(errors, 'signatureHash')}>
                      <Input placeholder="K8a/AINcGX7" className="font-mono" {...register('signatureHash')} />
                    </Field>
                  </div>
                )}
              </Section>
            ) : (
              <>
                <Section title="Header" description="Optional. A short title or a media sample shown above the message.">
                  <Field label="Header type" error={errorAt(errors, 'headerType')} className="max-w-xs">
                    <Select options={headerOptions} {...register('headerType')} />
                  </Field>

                  {values.headerType === 'TEXT' && (
                    <>
                      <Field
                        label="Header text"
                        required
                        hint={
                          <>
                            <Counter value={values.headerText} max={HEADER_TEXT_MAX_LENGTH} /> · One variable allowed.
                          </>
                        }
                        error={errorAt(errors, 'headerText')}
                      >
                        <div className="flex gap-2">
                          <Input
                            {...headerField}
                            ref={(element) => {
                              headerField.ref(element)
                              headerRef.current = element
                            }}
                            className="flex-1"
                            placeholder="Order {{1}} is on its way"
                          />
                          <Button
                            variant="secondary"
                            disabled={headerHasVariable}
                            onClick={() => insertAtCursor('headerText', headerRef.current, '{{1}}')}
                          >
                            Add variable
                          </Button>
                        </div>
                      </Field>
                      {headerHasVariable && (
                        <Field label="Example for {{1}} in the header" required error={errorAt(errors, 'headerExample')} className="sm:max-w-sm">
                          <Input placeholder="SS-10482" {...register('headerExample')} />
                        </Field>
                      )}
                    </>
                  )}

                  {values.headerType !== 'NONE' && values.headerType !== 'TEXT' && (
                    <Field
                      label="Sample media handle"
                      hint={
                        values.headerType === 'LOCATION'
                          ? 'Location headers need no sample. You send the location with each message.'
                          : "Meta asks for a sample file when reviewing media headers and may reject the template without one. Uploading samples from UpChatz isn't available yet; paste a handle from Meta's resumable upload API if you have one. You attach the real media when sending."
                      }
                      error={errorAt(errors, 'headerHandle')}
                    >
                      <Input className="font-mono" placeholder="4::aW1hZ2UvanBlZw==:ARb..." disabled={values.headerType === 'LOCATION'} {...register('headerHandle')} />
                    </Field>
                  )}
                </Section>

                <Section
                  title="Body"
                  description="The main message. Use *bold*, _italic_ and ~strikethrough~. Variables are filled per customer when sending."
                >
                  <Field
                    label="Message text"
                    required
                    hint={
                      <>
                        <Counter value={values.bodyText} max={BODY_MAX_LENGTH} /> · Number variables {'{{1}}'}, {'{{2}}'}… in order. The text can&apos;t start or end
                        with a variable.
                      </>
                    }
                    error={errorAt(errors, 'bodyText')}
                  >
                    <Textarea
                      rows={6}
                      {...bodyField}
                      ref={(element) => {
                        bodyField.ref(element)
                        bodyRef.current = element
                      }}
                      onChange={(event) => {
                        padExamples(event.target.value)
                        void bodyField.onChange(event)
                      }}
                      placeholder="Namaste {{1}}, your order of {{2}} has been shipped."
                    />
                  </Field>
                  <div>
                    <Button variant="secondary" size="sm" onClick={() => insertAtCursor('bodyText', bodyRef.current, `{{${nextVariable(values.bodyText)}}}`)}>
                      Add variable {`{{${nextVariable(values.bodyText)}}}`}
                    </Button>
                  </div>

                  {bodyVariables.length > 0 && (
                    <div className="rounded-lg border border-line-2 bg-paper/50 p-4">
                      <p className="text-[13px] font-medium text-ink">Example values</p>
                      <p className="mt-0.5 text-[13px] text-muted">
                        Meta requires a realistic example for every variable. They appear in the preview and are used only for review.
                      </p>
                      {errorAt(errors, 'bodyExamples') && <p className="mt-1 text-[13px] text-signal">{errorAt(errors, 'bodyExamples')}</p>}
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        {bodyVariables.map((n) => (
                          <Field key={n} label={`Example for {{${n}}}`} required error={errorAt(errors, `bodyExamples.${n - 1}`)}>
                            <Input {...register(`bodyExamples.${n - 1}`)} />
                          </Field>
                        ))}
                      </div>
                    </div>
                  )}
                </Section>

                <Section title="Footer" description="Optional short text under the message, such as “Reply STOP to opt out”. No variables.">
                  <Field label="Footer text" hint={<Counter value={values.footerText} max={FOOTER_MAX_LENGTH} />} error={errorAt(errors, 'footerText')}>
                    <Input placeholder="Sharma Sweets, Jaipur" {...register('footerText')} />
                  </Field>
                </Section>

                <Section title="Buttons" description="Optional. Quick replies let customers answer in one tap; call-to-action buttons open a link, call you or copy a code.">
                  <ButtonsEditor />
                </Section>
              </>
            )}

            <div className="flex flex-col gap-3">
              <ErrorSummary issues={issues} onSelect={(path) => setFocus(path as keyof BuilderValues)} />
              <FormAlert message={errors.root?.server?.message} />
              <p className="text-[13px] text-muted">
                Submitting sends the template to Meta for review. Reviews often finish within minutes but can take up to 24 hours, and Meta may reject or
                recategorise it.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button type="submit" loading={isSubmitting}>
                  {editing ? 'Save and submit for review' : 'Submit for review'}
                </Button>
                <Link to={editing ? `${templatesPath}/${editing.id}` : templatesPath} className={buttonClasses('ghost')}>
                  Cancel
                </Link>
              </div>
            </div>
          </div>

          <aside aria-label="Preview" className="flex flex-col gap-2 lg:sticky lg:top-6">
            <h2 className="font-display text-base font-semibold tracking-[-0.01em] text-ink">Preview</h2>
            <WhatsAppMessagePreview message={previewFromValues(values)} time="10:24 AM" />
            <p className="text-[12.5px] text-muted">
              {isAuth ? 'Shown with a sample code. Meta sets the exact wording.' : 'Shown with your example values. Customers see the values you send.'}
            </p>
          </aside>
        </form>
      </div>
    </FormProvider>
  )
}
