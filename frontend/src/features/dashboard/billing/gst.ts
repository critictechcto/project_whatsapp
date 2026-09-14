import { z } from 'zod'

/** GST state and union territory codes (the first two digits of a GSTIN). */
export const GST_STATES: readonly { code: string; name: string }[] = [
  { code: '01', name: 'Jammu and Kashmir' },
  { code: '02', name: 'Himachal Pradesh' },
  { code: '03', name: 'Punjab' },
  { code: '04', name: 'Chandigarh' },
  { code: '05', name: 'Uttarakhand' },
  { code: '06', name: 'Haryana' },
  { code: '07', name: 'Delhi' },
  { code: '08', name: 'Rajasthan' },
  { code: '09', name: 'Uttar Pradesh' },
  { code: '10', name: 'Bihar' },
  { code: '11', name: 'Sikkim' },
  { code: '12', name: 'Arunachal Pradesh' },
  { code: '13', name: 'Nagaland' },
  { code: '14', name: 'Manipur' },
  { code: '15', name: 'Mizoram' },
  { code: '16', name: 'Tripura' },
  { code: '17', name: 'Meghalaya' },
  { code: '18', name: 'Assam' },
  { code: '19', name: 'West Bengal' },
  { code: '20', name: 'Jharkhand' },
  { code: '21', name: 'Odisha' },
  { code: '22', name: 'Chhattisgarh' },
  { code: '23', name: 'Madhya Pradesh' },
  { code: '24', name: 'Gujarat' },
  { code: '26', name: 'Dadra and Nagar Haveli and Daman and Diu' },
  { code: '27', name: 'Maharashtra' },
  { code: '29', name: 'Karnataka' },
  { code: '30', name: 'Goa' },
  { code: '31', name: 'Lakshadweep' },
  { code: '32', name: 'Kerala' },
  { code: '33', name: 'Tamil Nadu' },
  { code: '34', name: 'Puducherry' },
  { code: '35', name: 'Andaman and Nicobar Islands' },
  { code: '36', name: 'Telangana' },
  { code: '37', name: 'Andhra Pradesh' },
  { code: '38', name: 'Ladakh' },
  { code: '97', name: 'Other Territory' },
]

const stateCodes = new Set(GST_STATES.map((state) => state.code))

/** Same pattern the backend enforces: 2-digit state, PAN, entity number, `Z`, check character. */
export const GSTIN_PATTERN = /^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/

export function normalizeGstin(value: string): string {
  return value.replace(/\s+/g, '').toUpperCase()
}

export function stateName(code: string): string | undefined {
  return GST_STATES.find((state) => state.code === code)?.name
}

/** Error for the GSTIN field, or null. An empty GSTIN is allowed (not GST-registered). */
export function gstinError(value: string): string | null {
  const gstin = normalizeGstin(value)
  if (!gstin) return null
  if (gstin.length !== 15) return 'A GSTIN has 15 characters.'
  if (!GSTIN_PATTERN.test(gstin)) return 'Enter a valid GSTIN, like 29ABCDE1234F1Z5.'
  if (!stateCodes.has(gstin.slice(0, 2))) return "The first two digits aren't a valid GST state code."
  return null
}

/** Error for the state field given the GSTIN, or null. */
export function stateCodeError(gstinValue: string, stateCode: string): string | null {
  if (!stateCode || !stateCodes.has(stateCode)) return 'Choose a state.'
  const gstin = normalizeGstin(gstinValue)
  if (gstin && GSTIN_PATTERN.test(gstin) && gstin.slice(0, 2) !== stateCode) {
    return 'Must match the first two digits of the GSTIN.'
  }
  return null
}

/** The state code implied by a valid GSTIN, used to pre-fill the state. */
export function stateFromGstin(value: string): string | null {
  const gstin = normalizeGstin(value)
  return !gstinError(gstin) && gstin ? gstin.slice(0, 2) : null
}

export const billingProfileSchema = z
  .object({
    legal_name: z.string().trim().min(1, 'Enter the legal name for invoices.').max(200, 'Use 200 characters or fewer.'),
    gstin: z.string(),
    email: z.email('Enter a valid email address.'),
    address_line1: z.string().trim().min(1, 'Enter the address.').max(200, 'Use 200 characters or fewer.'),
    address_line2: z.string().trim().max(200, 'Use 200 characters or fewer.'),
    city: z.string().trim().min(1, 'Enter the city.').max(100, 'Use 100 characters or fewer.'),
    state_code: z.string(),
    postal_code: z.string().trim().regex(/^\d{6}$/, 'Enter a 6-digit PIN code.'),
  })
  .superRefine((values, ctx) => {
    const gstin = gstinError(values.gstin)
    if (gstin) ctx.addIssue({ code: 'custom', path: ['gstin'], message: gstin })
    const state = stateCodeError(values.gstin, values.state_code)
    if (state) ctx.addIssue({ code: 'custom', path: ['state_code'], message: state })
  })

export type BillingProfileValues = z.infer<typeof billingProfileSchema>
