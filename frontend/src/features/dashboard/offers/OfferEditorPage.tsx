import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router'
import { applyApiErrorToForm, errorMessage, isApiError } from '../../../api/errors'
import {
  Button,
  buttonClasses,
  EmptyState,
  Field,
  Input,
  PageHeader,
  PageSpinner,
  Select,
  Switch,
  Textarea,
  useToast,
  WhatsAppMessagePreview,
} from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { ConfirmDialog } from '../campaigns/components/ConfirmDialog'
import { Notice } from '../campaigns/components/Notice'
import { RadioCards } from '../campaigns/components/RadioCards'
import { isCommerceUnavailable, offerKeys, offersApi, useOfferCode } from './api'
import { OffersUpgradePanel } from './components/OffersUpgradePanel'
import { appliesToLabels } from './format'
import { formToBody, MAX_REPLY, MAX_TITLE, offerFieldMap, offerFormFields, offerSchema, offerToForm, type OfferFormValues } from './offerForm'
import type { OfferAppliesTo, OfferCode, OfferDiscountType } from './types'

function Section({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  const id = `offer-section-${title.toLowerCase().replace(/\W+/g, '-')}`
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

export function OfferEditorPage() {
  const { id } = useParams()
  const { workspaceId } = useWorkspace()
  const offer = useOfferCode(workspaceId, id)

  if (id && offer.isPending) return <PageSpinner />
  if (id && offer.isError) {
    if (isCommerceUnavailable(offer.error)) return <OffersUpgradePanel />
    const missing = isApiError(offer.error) && offer.error.status === 404
    return (
      <EmptyState
        title={missing ? 'Offer code not found' : "Couldn't load this offer code"}
        description={missing ? 'It may have been deleted.' : errorMessage(offer.error)}
        action={
          <Link to={`/app/w/${workspaceId}/offers`} className={buttonClasses('secondary')}>
            Back to offers
          </Link>
        }
      />
    )
  }
  return <OfferEditor key={id ?? 'new'} offer={id ? (offer.data ?? null) : null} />
}

const discountOptions: { value: OfferDiscountType; label: string; description: string }[] = [
  { value: 'percent', label: 'Percent off', description: 'Like 15% off the order, with an optional cap.' },
  { value: 'amount', label: 'Amount off', description: 'A fixed amount, like ₹100 off.' },
  { value: 'none', label: 'Message only', description: 'No discount: send the reply and count who asked.' },
]

/** Reply buttons the bot adds when the store is on (docs/contracts/services-and-offers.md, Inbound). */
const previewButtons = [
  { type: 'QUICK_REPLY', text: 'Shop now' },
  { type: 'QUICK_REPLY', text: 'Menu' },
]

function OfferEditor({ offer }: { offer: OfferCode | null }) {
  const { workspaceId, timeZone } = useWorkspace()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const base = `/app/w/${workspaceId}/offers`

  const [initialValues] = useState(() => offerToForm(offer, timeZone))
  const {
    control,
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<OfferFormValues>({ resolver: zodResolver(offerSchema), defaultValues: initialValues })
  const discountType = useWatch({ control, name: 'discount_type' })
  const replyText = useWatch({ control, name: 'reply_text' })
  const [locked, setLocked] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const onSubmit = handleSubmit(async (values) => {
    const body = formToBody(values, timeZone)
    try {
      const saved = offer ? await offersApi.updateCode(offer.id, body) : await offersApi.createCode(body)
      queryClient.setQueryData(offerKeys.detail(workspaceId, saved.id), saved)
      void queryClient.invalidateQueries({ queryKey: offerKeys.all(workspaceId) })
      toast({ title: offer ? 'Offer code saved' : 'Offer code created', tone: 'success' })
      navigate(`${base}/${saved.id}`)
    } catch (error) {
      if (isCommerceUnavailable(error)) {
        setLocked(true)
        return
      }
      applyApiErrorToForm(error, setError, { fieldMap: offerFieldMap(values.discount_type), fields: offerFormFields })
    }
  })

  async function remove() {
    if (!offer) return
    setDeleting(true)
    try {
      await offersApi.deleteCode(offer.id)
      queryClient.removeQueries({ queryKey: offerKeys.detail(workspaceId, offer.id) })
      void queryClient.invalidateQueries({ queryKey: offerKeys.lists(workspaceId) })
      toast({ title: 'Offer code deleted', tone: 'success' })
      navigate(base)
    } catch (error) {
      setConfirmDelete(false)
      if (isApiError(error, 'offer_in_use')) {
        toast({
          title: `${offer.code} has been used, so it can't be deleted`,
          description: 'Turn it off instead: customers who send it then get no offer, and its history stays.',
          tone: 'error',
        })
      } else {
        toast({ title: "Couldn't delete the offer code", description: errorMessage(error), tone: 'error' })
      }
    } finally {
      setDeleting(false)
    }
  }

  if (locked) return <OffersUpgradePanel />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={offer ? `${base}/${offer.id}` : base} className="hover:text-ink">
            {offer ? offer.code : 'Offers'}
          </Link>
        }
        title={offer ? `Edit ${offer.code}` : 'New offer code'}
        description="Customers send this code on WhatsApp, exactly as written, and get your reply."
        actions={
          offer ? (
            <Button variant="ghost" icon={<Trash2 className="size-4" aria-hidden="true" />} onClick={() => setConfirmDelete(true)}>
              Delete
            </Button>
          ) : null
        }
      />

      <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-8">
        {errors.root?.server?.message && <Notice tone="error">{errors.root.server.message}</Notice>}

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="flex min-w-0 flex-col gap-8">
            <Section title="Code and reply">
              <Field label="Code" hint="2 to 20 letters, digits, - or _. Customers can type it in any case." error={errors.code?.message} required>
                <Input
                  {...register('code', {
                    onChange: (event: { target: { value: string } }) => setValue('code', event.target.value.toUpperCase()),
                  })}
                  maxLength={20}
                  autoComplete="off"
                  autoCapitalize="characters"
                  spellCheck={false}
                  placeholder="DIWALI"
                  className="font-mono uppercase"
                />
              </Field>
              <Field label="Title" hint="For your team; customers don't see it." error={errors.title?.message} required>
                <Input {...register('title')} maxLength={MAX_TITLE} autoComplete="off" placeholder="Diwali 15% off" />
              </Field>
              <Field
                label="Reply message"
                hint={`What customers get when they send the code. Up to ${MAX_REPLY} characters; *bold* and _italic_ work.`}
                error={errors.reply_text?.message}
                required
              >
                <Textarea {...register('reply_text')} rows={5} maxLength={MAX_REPLY} />
              </Field>
            </Section>

            <Section title="Discount" description="Applied at the customer's next checkout on WhatsApp, or by your staff at the counter.">
              <Controller
                control={control}
                name="discount_type"
                render={({ field }) => (
                  <RadioCards legend="Type" hideLegend value={field.value} onChange={field.onChange} options={discountOptions} columns={1} />
                )}
              />
              {discountType === 'percent' && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Discount percent" error={errors.percent?.message} required>
                    <Input {...register('percent')} inputMode="numeric" autoComplete="off" placeholder="15" />
                  </Field>
                  <Field label="Up to" hint="Optional cap on the discount." error={errors.max_discount?.message}>
                    <Input {...register('max_discount')} prefix="₹" inputMode="decimal" autoComplete="off" placeholder="300" />
                  </Field>
                </div>
              )}
              {discountType === 'amount' && (
                <Field label="Amount off" error={errors.amount?.message} required className="sm:max-w-xs">
                  <Input {...register('amount')} prefix="₹" inputMode="decimal" autoComplete="off" placeholder="100" />
                </Field>
              )}
              {discountType !== 'none' && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Minimum order" hint="Optional. Checked on the order subtotal." error={errors.min_order?.message}>
                    <Input {...register('min_order')} prefix="₹" inputMode="decimal" autoComplete="off" placeholder="500" />
                  </Field>
                  <Field label="Applies to" error={errors.applies_to?.message}>
                    <Select
                      {...register('applies_to')}
                      options={(Object.keys(appliesToLabels) as OfferAppliesTo[]).map((value) => ({ value, label: appliesToLabels[value] }))}
                    />
                  </Field>
                </div>
              )}
            </Section>

            <Section title="When and how often" description={`Dates are whole days in your workspace time zone (${timeZone}).`}>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Starts on" hint="Leave empty to start now." error={errors.starts_on?.message}>
                  <Input {...register('starts_on')} type="date" />
                </Field>
                <Field label="Ends on" hint="Leave empty for no end date." error={errors.ends_on?.message}>
                  <Input {...register('ends_on')} type="date" />
                </Field>
                <Field label="Total uses" hint="Optional. Counts orders and counter redemptions." error={errors.max_uses?.message}>
                  <Input {...register('max_uses')} inputMode="numeric" autoComplete="off" placeholder="Unlimited" />
                </Field>
                <Field label="Uses per customer" error={errors.max_uses_per_contact?.message} required>
                  <Input {...register('max_uses_per_contact')} inputMode="numeric" autoComplete="off" />
                </Field>
              </div>
              <Controller
                control={control}
                name="is_active"
                render={({ field }) => (
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    label="Active"
                    description="When off, customers who send the code get no reply from it."
                  />
                )}
              />
            </Section>
          </div>

          <aside aria-label="Reply preview" className="flex flex-col gap-2 lg:sticky lg:top-4 lg:self-start">
            <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Reply preview</p>
            <WhatsAppMessagePreview message={{ body: replyText, buttons: previewButtons }} />
            <p className="text-[12px] text-muted">The buttons are added when your store is on.</p>
          </aside>
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-line pt-5 sm:flex-row sm:justify-end">
          <Link to={offer ? `${base}/${offer.id}` : base} className={buttonClasses('secondary', 'md', 'min-h-11 sm:min-h-0')}>
            Cancel
          </Link>
          <Button type="submit" loading={isSubmitting} className="min-h-11 sm:min-h-0">
            {offer ? 'Save changes' : 'Create code'}
          </Button>
        </div>
      </form>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${offer?.code ?? 'this code'}?`}
        description="Customers who send it will no longer get the offer. Codes that were already used can't be deleted; turn them off instead."
        confirmLabel="Delete code"
        onConfirm={() => void remove()}
        loading={deleting}
        danger
      />
    </div>
  )
}
