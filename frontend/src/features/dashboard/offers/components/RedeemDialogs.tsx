import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useId } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { applyApiErrorToForm, isApiError } from '../../../../api/errors'
import { Button, Dialog, Field, Input, useToast } from '../../../../components/app'
import { formatPaise, parseRupeesToPaise } from '../../../../lib/money'
import { useWorkspace } from '../../../../lib/workspace'
import { Notice } from '../../campaigns/components/Notice'
import { offerKeys, offersApi } from '../api'
import { formatPhone, normalisePhone } from '../format'
import type { OfferClaim } from '../types'

const bill = z.string().refine((value) => !value.trim() || parseRupeesToPaise(value) !== null, 'Enter the bill in rupees, like 1450.')

const billPaise = (value: string) => (value.trim() ? (parseRupeesToPaise(value) ?? undefined) : undefined)

/** Messages for the redeem endpoints' 409s. `offer_unavailable` comes from the server's own message. */
function conflictMessage(error: unknown): string | null {
  if (!isApiError(error) || error.status !== 409) return null
  if (error.code === 'invalid_transition') return 'This claim was already redeemed or has expired.'
  return error.message
}

const counterSchema = z.object({
  code: z
    .string()
    .trim()
    .min(1, 'Enter the offer code.'),
  phone: z
    .string()
    .trim()
    .min(1, "Enter the customer's WhatsApp number.")
    .refine((value) => normalisePhone(value) !== null, 'Enter a 10-digit mobile number, or the full number with +country code.'),
  bill,
})

type CounterValues = z.infer<typeof counterSchema>

type RedeemCounterDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Prefills the code (from a code's page). */
  defaultCode?: string
}

/** Records a walk-in customer using a code at the shop: `POST /api/v1/offers/redeem/`. */
export function RedeemCounterDialog({ open, onOpenChange, defaultCode = '' }: RedeemCounterDialogProps) {
  return open ? <RedeemCounterForm onOpenChange={onOpenChange} defaultCode={defaultCode} /> : null
}

function RedeemCounterForm({ onOpenChange, defaultCode }: { onOpenChange: (open: boolean) => void; defaultCode: string }) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const formId = useId()
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<CounterValues>({ resolver: zodResolver(counterSchema), defaultValues: { code: defaultCode, phone: '', bill: '' } })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const claim = await offersApi.redeemAtCounter({
        code: values.code.trim().toUpperCase(),
        phone: normalisePhone(values.phone) ?? values.phone,
        bill_paise: billPaise(values.bill),
      })
      void queryClient.invalidateQueries({ queryKey: offerKeys.all(workspaceId) })
      toast({
        title: 'Offer redeemed',
        description: `${values.code.trim().toUpperCase()} for ${claim.contact.name || formatPhone(claim.contact.phone_e164)}${claim.discount_paise ? `, ${formatPaise(claim.discount_paise)} off` : ''}.`,
        tone: 'success',
      })
      onOpenChange(false)
    } catch (error) {
      const conflict = conflictMessage(error)
      if (conflict) setError('root.server', { message: conflict })
      else applyApiErrorToForm(error, setError, { fieldMap: { bill_paise: 'bill' }, fields: ['code', 'phone', 'bill'] })
    }
  })

  return (
    <Dialog
      open
      onOpenChange={onOpenChange}
      dismissible={!isSubmitting}
      title="Redeem at counter"
      description="For a customer showing an offer at your shop. If they never claimed it on WhatsApp, it is recorded now."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" form={formId} loading={isSubmitting}>
            Redeem
          </Button>
        </>
      }
    >
      <form id={formId} noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4">
        {errors.root?.server?.message && <Notice tone="error">{errors.root.server.message}</Notice>}
        <Field label="Offer code" error={errors.code?.message} required>
          <Input
            {...register('code', {
              onChange: (event: { target: { value: string } }) => setValue('code', event.target.value.toUpperCase()),
            })}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={20}
            className="font-mono uppercase"
            placeholder="DIWALI"
          />
        </Field>
        <Field label="Customer's WhatsApp number" error={errors.phone?.message} required>
          <Input {...register('phone')} type="tel" inputMode="tel" autoComplete="off" placeholder="98765 43210" />
        </Field>
        <Field label="Bill amount" hint="Optional. Counts towards the revenue this offer brought in." error={errors.bill?.message}>
          <Input {...register('bill')} prefix="₹" inputMode="decimal" autoComplete="off" placeholder="1450" />
        </Field>
      </form>
    </Dialog>
  )
}

const claimSchema = z.object({ bill })
type ClaimValues = z.infer<typeof claimSchema>

type RedeemClaimDialogProps = {
  claim: OfferClaim | null
  code: string
  onOpenChange: (open: boolean) => void
}

/** Marks one open claim as redeemed: `POST /api/v1/offers/claims/{id}/redeem/`. */
export function RedeemClaimDialog({ claim, code, onOpenChange }: RedeemClaimDialogProps) {
  return claim ? <RedeemClaimForm key={claim.id} claim={claim} code={code} onOpenChange={onOpenChange} /> : null
}

function RedeemClaimForm({ claim, code, onOpenChange }: { claim: OfferClaim; code: string; onOpenChange: (open: boolean) => void }) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const formId = useId()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ClaimValues>({ resolver: zodResolver(claimSchema), defaultValues: { bill: '' } })
  const who = claim.contact.name || formatPhone(claim.contact.phone_e164)

  const onSubmit = handleSubmit(async (values) => {
    try {
      await offersApi.redeemClaim(claim.id, { bill_paise: billPaise(values.bill) })
      void queryClient.invalidateQueries({ queryKey: offerKeys.all(workspaceId) })
      toast({ title: 'Offer redeemed', description: `${code} for ${who}.`, tone: 'success' })
      onOpenChange(false)
    } catch (error) {
      const conflict = conflictMessage(error)
      if (conflict) {
        void queryClient.invalidateQueries({ queryKey: offerKeys.all(workspaceId) })
        setError('root.server', { message: conflict })
      } else applyApiErrorToForm(error, setError, { fieldMap: { bill_paise: 'bill' }, fields: ['bill'] })
    }
  })

  return (
    <Dialog
      open
      size="sm"
      onOpenChange={onOpenChange}
      dismissible={!isSubmitting}
      title={`Redeem ${code}`}
      description={`Mark ${who}'s offer as used at your shop.`}
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" form={formId} loading={isSubmitting}>
            Redeem
          </Button>
        </>
      }
    >
      <form id={formId} noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4">
        {errors.root?.server?.message && <Notice tone="error">{errors.root.server.message}</Notice>}
        <Field label="Bill amount" hint="Optional." error={errors.bill?.message}>
          <Input {...register('bill')} prefix="₹" inputMode="decimal" autoComplete="off" placeholder="1450" />
        </Field>
      </form>
    </Dialog>
  )
}
