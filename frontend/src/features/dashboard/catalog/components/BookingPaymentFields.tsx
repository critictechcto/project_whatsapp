import { TriangleAlert } from 'lucide-react'
import { useWatch, type Control, type FieldErrors, type UseFormRegister } from 'react-hook-form'
import { Link } from 'react-router'
import { Field, FieldError, Input, Select } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { useWorkspace } from '../../../../lib/workspace'
import { usePaymentAccount } from '../../store/api'
import { bookingPaymentLabels } from '../lib/labels'
import { MAX_ADVANCE_PERCENT, MIN_ADVANCE_PERCENT, type ProductFormValues } from '../lib/productForm'
import { bookingPaymentValues, type AdvanceType } from '../lib/types'

const paymentHints = {
  store_default: 'Buyers pay as your store allows: online, or at the shop when that is on in Store → Bookings.',
  advance: 'Buyers pay this online when they book; the rest at the shop.',
  full: 'Buyers pay the full price online when they book.',
} as const

const advanceTypeOptions: ReadonlyArray<{ value: AdvanceType; label: string }> = [
  { value: 'amount', label: '₹ amount' },
  { value: 'percent', label: '% of price' },
]

type Props = {
  control: Control<ProductFormValues>
  register: UseFormRegister<ProductFormValues>
  errors: FieldErrors<ProductFormValues>
}

/** "Payment at booking" for services: the store setting, an advance (₹ or %) or full payment online. */
export function BookingPaymentFields({ control, register, errors }: Props) {
  const { workspaceId } = useWorkspace()
  const account = usePaymentAccount(workspaceId)
  const [payment, advanceType] = useWatch({ control, name: ['bookingPayment', 'advanceType'] })
  const needsOnline = payment === 'advance' || payment === 'full'
  // Matches the backend's online_payments_ready(): only a verified gateway account takes payments.
  const onlineMissing = needsOnline && account.isSuccess && account.data.status !== 'verified'

  return (
    <section aria-labelledby="product-booking-payment" className="flex flex-col gap-4 rounded-xl border border-line bg-card p-5">
      <h2 id="product-booking-payment" className="font-display text-base font-semibold text-ink">
        Payment at booking
      </h2>
      <Field label="Payment at booking" hideLabel error={errors.bookingPayment?.message} hint={paymentHints[payment]} className="sm:max-w-[calc(50%-0.5rem)]">
        <Select options={bookingPaymentValues.map((value) => ({ value, label: bookingPaymentLabels[value] }))} {...register('bookingPayment')} />
      </Field>

      {payment === 'advance' && (
        <div className="grid gap-4 sm:grid-cols-2">
          <fieldset className="flex min-w-0 flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium text-ink">
              Advance in
            </legend>
            <div className="inline-flex w-fit rounded-lg border border-line bg-paper-2/70 p-1">
              {advanceTypeOptions.map((option) => (
                <label
                  key={option.value}
                  className={cn(
                    'inline-flex min-h-11 cursor-pointer items-center rounded-md px-4 text-sm font-medium transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent',
                    advanceType === option.value ? 'bg-card text-ink shadow-sm ring-1 ring-line' : 'text-muted hover:text-ink',
                  )}
                >
                  <input type="radio" value={option.value} className="sr-only" {...register('advanceType')} />
                  {option.label}
                </label>
              ))}
            </div>
            <FieldError>{errors.advanceType?.message}</FieldError>
          </fieldset>
          {advanceType === 'amount' ? (
            <Field label="Advance (₹)" required error={errors.advanceValue?.message} hint="At least ₹1 and less than the price.">
              <Input inputMode="decimal" prefix="₹" placeholder="200" {...register('advanceValue')} />
            </Field>
          ) : (
            <Field label="Advance (%)" required error={errors.advanceValue?.message} hint={`${MIN_ADVANCE_PERCENT} to ${MAX_ADVANCE_PERCENT} percent of the price.`}>
              <Input inputMode="numeric" placeholder="20" {...register('advanceValue')} />
            </Field>
          )}
        </div>
      )}

      {onlineMissing && (
        <div role="status" className="flex items-start gap-2 rounded-lg border border-amber/25 bg-amber-soft/70 px-3 py-2.5 text-[13px] text-ink-2">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber" aria-hidden="true" />
          <p>
            Buyers can't book this service until online payments are set up.{' '}
            <Link to={`/app/w/${workspaceId}/store/payments`} className="font-medium text-accent-2 underline underline-offset-2">
              Store → Payments
            </Link>
          </p>
        </div>
      )}
    </section>
  )
}
