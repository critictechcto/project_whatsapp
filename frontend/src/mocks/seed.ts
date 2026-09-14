/**
 * Seeded Indian sample data for mock mode and tests. Deterministic: fixed ids and timestamps.
 * Feature areas import these constants (and the generators) to build their own mock data.
 */

export const DEMO_PASSWORD = 'demo12345'

export const ids = {
  demoUser: '0b6c2f1e-8a41-4d7e-9c55-1f0a7b3e2d01',
  priya: '0b6c2f1e-8a41-4d7e-9c55-1f0a7b3e2d02',
  arjun: '0b6c2f1e-8a41-4d7e-9c55-1f0a7b3e2d03',
  farhan: '0b6c2f1e-8a41-4d7e-9c55-1f0a7b3e2d04',
  /** Primary demo workspace: a sweet shop in Jaipur. */
  sharmaSweets: '5a1d7c9e-3b2f-4e6a-8d10-2c4b6e8f0a11',
  /** Second workspace to try the switcher: a dental clinic in Bengaluru. */
  kaveriClinic: '5a1d7c9e-3b2f-4e6a-8d10-2c4b6e8f0a12',
  /** Workspace the demo user has a pending invitation to. */
  anandTextiles: '5a1d7c9e-3b2f-4e6a-8d10-2c4b6e8f0a13',
  waba: '7e3a9b1c-5d2f-4a8e-b6c0-9f1e3d5a7b21',
  phoneMain: '7e3a9b1c-5d2f-4a8e-b6c0-9f1e3d5a7b22',
} as const

export const DEMO_EMAIL = 'demo@upchatz.com'
export const DEMO_INVITE_TOKEN = 'demo-invite-token'

/** Fixed reference time so relative dates in the demo look recent but tests stay stable. */
export const SEED_NOW = '2026-09-10T09:30:00Z'

export function daysAgo(days: number, from = SEED_NOW): string {
  return new Date(new Date(from).getTime() - days * 86_400_000).toISOString()
}

export const seedUsers = [
  { id: ids.demoUser, email: DEMO_EMAIL, full_name: 'Rohan Sharma', date_joined: daysAgo(120) },
  { id: ids.priya, email: 'priya.nair@sharmasweets.in', full_name: 'Priya Nair', date_joined: daysAgo(90) },
  { id: ids.arjun, email: 'arjun.mehta@sharmasweets.in', full_name: 'Arjun Mehta', date_joined: daysAgo(60) },
  { id: ids.farhan, email: 'farhan.qureshi@kavericlinic.in', full_name: 'Farhan Qureshi', date_joined: daysAgo(45) },
] as const

export const seedWorkspaces = [
  { id: ids.sharmaSweets, name: 'Sharma Sweets', slug: 'sharma-sweets', time_zone: 'Asia/Kolkata', created_at: daysAgo(120) },
  { id: ids.kaveriClinic, name: 'Kaveri Dental Clinic', slug: 'kaveri-dental-clinic', time_zone: 'Asia/Kolkata', created_at: daysAgo(40) },
  { id: ids.anandTextiles, name: 'Anand Textiles', slug: 'anand-textiles', time_zone: 'Asia/Kolkata', created_at: daysAgo(200) },
] as const

export const seedMemberships = [
  { workspace_id: ids.sharmaSweets, user_id: ids.demoUser, role: 'owner', created_at: daysAgo(120) },
  { workspace_id: ids.sharmaSweets, user_id: ids.priya, role: 'admin', created_at: daysAgo(90) },
  { workspace_id: ids.sharmaSweets, user_id: ids.arjun, role: 'agent', created_at: daysAgo(60) },
  { workspace_id: ids.kaveriClinic, user_id: ids.demoUser, role: 'admin', created_at: daysAgo(40) },
  { workspace_id: ids.kaveriClinic, user_id: ids.farhan, role: 'owner', created_at: daysAgo(40) },
  { workspace_id: ids.anandTextiles, user_id: ids.farhan, role: 'owner', created_at: daysAgo(200) },
] as const

const firstNames = [
  'Aarav', 'Ananya', 'Vihaan', 'Diya', 'Aditya', 'Ishita', 'Kabir', 'Meera', 'Reyansh', 'Saanvi',
  'Arnav', 'Kavya', 'Vivaan', 'Tara', 'Rudra', 'Nisha', 'Yash', 'Pooja', 'Imran', 'Harpreet',
  'Lakshmi', 'Suresh', 'Gurleen', 'Joseph', 'Fatima', 'Venkat', 'Sneha', 'Rahul', 'Anjali', 'Deepak',
] as const

const lastNames = [
  'Patel', 'Iyer', 'Reddy', 'Gupta', 'Singh', 'Das', 'Menon', 'Khan', 'Joshi', 'Banerjee',
  'Kulkarni', 'Pillai', 'Chauhan', 'Rao', 'Verma', 'Mukherjee', 'Nair', 'Agarwal', 'Fernandes', 'Bhat',
] as const

export const indianCities = [
  'Mumbai', 'Delhi', 'Bengaluru', 'Hyderabad', 'Chennai', 'Kolkata', 'Pune', 'Ahmedabad', 'Jaipur', 'Lucknow',
  'Kochi', 'Indore', 'Chandigarh', 'Surat', 'Coimbatore',
] as const

/** Deterministic full name for index `i`. */
export function indianName(i: number): string {
  return `${firstNames[i % firstNames.length]} ${lastNames[(i * 7) % lastNames.length]}`
}

/** Deterministic Indian mobile number in E.164 (`+91` + 10 digits starting 6–9). */
export function indianMobile(i: number): string {
  const lead = 9 - (i % 4)
  const rest = String((i * 7_919_393 + 12_345_678) % 1_000_000_000).padStart(9, '0')
  return `+91${lead}${rest}`
}

/** `+919876543210` → `+91 98765 43210`. */
export function displayIndianNumber(e164: string): string {
  const digits = e164.replace(/^\+91/, '')
  return digits.length === 10 ? `+91 ${digits.slice(0, 5)} ${digits.slice(5)}` : e164
}

/** Rupees → paise, for billing amounts (`*_paise`). */
export function rupeesToPaise(rupees: number): number {
  return Math.round(rupees * 100)
}

export const seedWaba = {
  id: ids.waba,
  waba_id: '102938475610293',
  business_id: '564738291056473',
  name: 'Sharma Sweets',
  currency: 'INR',
  timezone_id: '71',
  message_template_namespace: 'b1c2d3e4_f5a6_7b8c_9d0e_1f2a3b4c5d6e',
  status: 'active',
  onboarding_status: 'completed',
  last_error: '',
  subscribed_at: daysAgo(100),
  token_expires_at: null,
  connected_by: ids.demoUser,
  created_at: daysAgo(100),
  updated_at: daysAgo(1),
} as const

/** Template seeds in Meta's component format. Ids are stable for tests. */
export const seedTemplates = [
  {
    id: 'a4e1c3b5-7d9f-4b2a-8c6e-0f1a2b3c4d51',
    name: 'order_shipped',
    language: 'en',
    category: 'UTILITY',
    status: 'APPROVED',
    components: [
      { type: 'HEADER', format: 'TEXT', text: 'Order {{1}} is on its way' },
      {
        type: 'BODY',
        text: 'Namaste {{1}}, your order of *{{2}}* has been shipped and will reach you by {{3}}.',
        example: { body_text: [['Ananya', '1 kg Kaju Katli', '14 Sep']] },
      },
      { type: 'FOOTER', text: 'Sharma Sweets, Jaipur' },
      {
        type: 'BUTTONS',
        buttons: [
          { type: 'URL', text: 'Track order', url: 'https://sharmasweets.in/track/{{1}}' },
          { type: 'QUICK_REPLY', text: 'Talk to us' },
        ],
      },
    ],
  },
  {
    id: 'a4e1c3b5-7d9f-4b2a-8c6e-0f1a2b3c4d52',
    name: 'diwali_early_access',
    language: 'en',
    category: 'MARKETING',
    status: 'APPROVED',
    components: [
      { type: 'HEADER', format: 'IMAGE', example: { header_handle: ['https://example.invalid/diwali.jpg'] } },
      {
        type: 'BODY',
        text: 'Hi {{1}}, our Diwali gift boxes are here. Order before {{2}} and get free delivery within Jaipur.',
        example: { body_text: [['Kabir', '20 Oct']] },
      },
      { type: 'FOOTER', text: 'Reply STOP to opt out' },
      { type: 'BUTTONS', buttons: [{ type: 'QUICK_REPLY', text: 'Show gift boxes' }] },
    ],
  },
  {
    id: 'a4e1c3b5-7d9f-4b2a-8c6e-0f1a2b3c4d53',
    name: 'payment_reminder_hi',
    language: 'hi',
    category: 'UTILITY',
    status: 'PENDING',
    components: [
      {
        type: 'BODY',
        text: 'नमस्ते {{1}}, ₹{{2}} का भुगतान {{3}} तक बाकी है।',
        example: { body_text: [['Meera', '1,250', '15 Sep']] },
      },
    ],
  },
  {
    id: 'a4e1c3b5-7d9f-4b2a-8c6e-0f1a2b3c4d54',
    name: 'feedback_request',
    language: 'en',
    category: 'MARKETING',
    status: 'REJECTED',
    rejected_reason: 'INVALID_FORMAT',
    components: [{ type: 'BODY', text: 'Hi {{1}}, how was your order? Rate us 1-5.' }],
  },
] as const

export const seedTags = [
  { id: 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e61', name: 'Regular customer', color: '#1d7f55', created_at: daysAgo(80) },
  { id: 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e62', name: 'Diwali 2026', color: '#a3461f', created_at: daysAgo(20) },
  { id: 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e63', name: 'Wholesale', color: '#8a5d0c', created_at: daysAgo(70) },
] as const

export const seedPhoneNumber = {
  id: ids.phoneMain,
  waba: ids.waba,
  phone_number_id: '109876543210987',
  display_phone_number: '+91 98290 11223',
  phone_e164: '+919829011223',
  verified_name: 'Sharma Sweets',
  name_status: 'APPROVED',
  quality_rating: 'GREEN',
  messaging_limit_tier: 'TIER_1K',
  throughput_level: 'STANDARD',
  platform_type: 'CLOUD_API',
  code_verification_status: 'VERIFIED',
  meta_status: 'CONNECTED',
  registration_status: 'registered',
  is_coexistence: false,
  is_default: true,
  last_synced_at: daysAgo(1),
  last_error: '',
  created_at: daysAgo(100),
  updated_at: daysAgo(1),
} as const
