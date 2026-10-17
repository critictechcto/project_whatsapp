/**
 * In-memory offer codes and claims for mock mode and tests, rebuilt whenever the shared mock
 * database is reset (before each test). Contacts and the linked order use the same ids as the
 * orders and contacts mocks.
 */
import { db, type Mutable } from '../../../mocks/db'
import { ids, indianMobile, indianName } from '../../../mocks/seed'
import type { OfferClaim, OfferCode } from './types'

export type MockOfferCode = Required<Mutable<Omit<OfferCode, 'claims_count' | 'redeemed_count'>>> & { workspaceId: string }
/** Stored claim; `offer_code` and `from_ad` are derived when serialized, as on the backend. */
export type MockClaim = Mutable<Omit<OfferClaim, 'offer_code' | 'from_ad'>> & { workspaceId: string }

export const offerIds = {
  diwali: '0ffe0000-0000-4000-8000-000000000001',
  kaju: '0ffe0000-0000-4000-8000-000000000002',
  welcome: '0ffe0000-0000-4000-8000-000000000003',
} as const

export const claimIds = {
  kabirOrder: '0ffec1a1-0000-4000-8000-000000000001',
  counter: '0ffec1a1-0000-4000-8000-000000000002',
  fromAd: '0ffec1a1-0000-4000-8000-000000000003',
  redeemedOnline: '0ffec1a1-0000-4000-8000-000000000004',
  plain: '0ffec1a1-0000-4000-8000-000000000005',
  secondAd: '0ffec1a1-0000-4000-8000-000000000006',
  kajuOpen: '0ffec1a1-0000-4000-8000-000000000007',
  kajuRedeemed: '0ffec1a1-0000-4000-8000-000000000008',
} as const

const CONTACT_PREFIX = 'e0f1a2b3-c4d5-4e6f-8a9b-'

export function mockContact(i: number): OfferClaim['contact'] {
  return {
    id: `${CONTACT_PREFIX}${String(i + 1).padStart(12, '0')}`,
    name: indianName(i),
    phone_e164: indianMobile(i),
    marketing_opt_in_status: i % 3 === 0 ? 'unknown' : 'opted_in',
  }
}

function build() {
  const now = Date.now()
  const hoursAgo = (hours: number) => new Date(now - hours * 3_600_000).toISOString()
  const daysAgo = (days: number) => hoursAgo(days * 24)
  const daysAhead = (days: number) => new Date(now + days * 86_400_000).toISOString()

  const codes: MockOfferCode[] = [
    {
      workspaceId: ids.sharmaSweets,
      id: offerIds.diwali,
      code: 'DIWALI',
      title: 'Diwali 15% off',
      reply_text:
        'Happy Diwali from Sharma Sweets! 🪔 Your code *DIWALI* gives you 15% off (up to ₹300) on orders above ₹500. It is applied automatically when you order here, or show this message at our counter.',
      discount_type: 'percent',
      discount_value: 15,
      max_discount_paise: 30_000,
      min_order_paise: 50_000,
      applies_to: 'all',
      starts_at: daysAgo(12),
      ends_at: daysAhead(20),
      max_uses: null,
      max_uses_per_contact: 1,
      is_active: true,
      created_at: daysAgo(14),
      updated_at: daysAgo(12),
    },
    {
      workspaceId: ids.sharmaSweets,
      id: offerIds.kaju,
      code: 'KAJU100',
      title: '₹100 off kaju katli boxes',
      reply_text: 'Here is ₹100 off your next kaju katli order of ₹999 or more. Tap *Shop now* to pick your box.',
      discount_type: 'amount',
      discount_value: 10_000,
      max_discount_paise: null,
      min_order_paise: 99_900,
      applies_to: 'products',
      starts_at: null,
      ends_at: null,
      max_uses: 200,
      max_uses_per_contact: 1,
      is_active: true,
      created_at: daysAgo(30),
      updated_at: daysAgo(30),
    },
    {
      workspaceId: ids.sharmaSweets,
      id: offerIds.welcome,
      code: 'NAMASTE',
      title: 'Welcome message',
      reply_text: 'Namaste! Thanks for writing to Sharma Sweets. Reply *MENU* to see today’s sweets.',
      discount_type: 'none',
      discount_value: 0,
      max_discount_paise: null,
      min_order_paise: 0,
      applies_to: 'all',
      starts_at: null,
      ends_at: null,
      max_uses: null,
      max_uses_per_contact: 1,
      is_active: false,
      created_at: daysAgo(60),
      updated_at: daysAgo(20),
    },
  ]

  const claim = (fields: Partial<MockClaim> & Pick<MockClaim, 'id' | 'offer' | 'status' | 'created_at'> & { contactIndex: number }): MockClaim => {
    const { contactIndex, ...rest } = fields
    return {
      workspaceId: ids.sharmaSweets,
      contact: mockContact(contactIndex),
      conversation_id: null,
      order_id: null,
      order_number: null,
      discount_paise: 0,
      bill_paise: null,
      ad_source_id: '',
      ad_source_url: '',
      ad_headline: '',
      ctwa_clid: '',
      redeemed_at: null,
      redeemed_by: null,
      ...rest,
    }
  }

  const claims: MockClaim[] = [
    claim({
      id: claimIds.kabirOrder,
      offer: offerIds.diwali,
      contactIndex: 6,
      status: 'applied',
      conversation_id: 'c3d4e5f6-a7b8-4c9d-8e0f-000000000010',
      order_id: '7d0a4e3c-9f6b-4a1c-a5e8-3b4c5d6e7f01',
      order_number: 'SS-1042',
      discount_paise: 18_000,
      ad_source_id: '120210000000000001',
      ad_source_url: 'https://fb.me/sharmasweets-diwali',
      ad_headline: 'Diwali sweets, 15% off on WhatsApp',
      ctwa_clid: 'ARAkLk3-diwali-1',
      created_at: hoursAgo(2),
    }),
    claim({
      id: claimIds.counter,
      offer: offerIds.diwali,
      contactIndex: 2,
      status: 'redeemed',
      discount_paise: 30_000,
      bill_paise: 245_000,
      redeemed_at: daysAgo(1),
      redeemed_by: userSummary(ids.demoUser),
      created_at: daysAgo(3),
    }),
    claim({
      id: claimIds.fromAd,
      offer: offerIds.diwali,
      contactIndex: 5,
      status: 'claimed',
      ad_source_id: '120210000000000002',
      ad_source_url: 'https://fb.me/sharmasweets-giftbox',
      ad_headline: 'Diwali gift boxes, 15% off',
      ctwa_clid: 'ARAkLk3-diwali-2',
      created_at: daysAgo(2),
    }),
    claim({
      id: claimIds.redeemedOnline,
      offer: offerIds.diwali,
      contactIndex: 7,
      status: 'redeemed',
      discount_paise: 18_000,
      bill_paise: 102_000,
      redeemed_at: daysAgo(4),
      created_at: daysAgo(6),
    }),
    claim({ id: claimIds.plain, offer: offerIds.diwali, contactIndex: 10, status: 'claimed', created_at: daysAgo(5) }),
    claim({
      id: claimIds.secondAd,
      offer: offerIds.diwali,
      contactIndex: 12,
      status: 'claimed',
      ad_source_id: '120210000000000001',
      ad_source_url: 'https://fb.me/sharmasweets-diwali',
      ad_headline: 'Diwali sweets, 15% off on WhatsApp',
      ctwa_clid: 'ARAkLk3-diwali-3',
      created_at: daysAgo(8),
    }),
    claim({ id: claimIds.kajuOpen, offer: offerIds.kaju, contactIndex: 1, status: 'claimed', created_at: daysAgo(9) }),
    claim({
      id: claimIds.kajuRedeemed,
      offer: offerIds.kaju,
      contactIndex: 8,
      status: 'redeemed',
      discount_paise: 10_000,
      bill_paise: 132_000,
      redeemed_at: daysAgo(10),
      created_at: daysAgo(11),
    }),
  ]

  return { codes, claims }
}

let snapshot: { token: unknown; state: ReturnType<typeof build> } | null = null

export function offerState() {
  if (!snapshot || snapshot.token !== db.generation) snapshot = { token: db.generation, state: build() }
  return snapshot.state
}

/** A code as the API returns it, with its counters. */
export function serializeCode(code: MockOfferCode): OfferCode {
  const { workspaceId, ...rest } = code
  void workspaceId
  const claims = offerState().claims.filter((claim) => claim.offer === code.id)
  return { ...rest, claims_count: claims.length, redeemed_count: claims.filter((claim) => claim.status === 'redeemed').length }
}

export function serializeClaim(claim: MockClaim): OfferClaim {
  const { workspaceId, ...rest } = claim
  void workspaceId
  const code = offerState().codes.find((item) => item.id === claim.offer)
  return { ...rest, offer_code: code?.code ?? '', from_ad: Boolean(claim.ad_source_id || claim.ctwa_clid) }
}

/** A dashboard member as `redeemed_by`. */
export function userSummary(userId: string): OfferClaim['redeemed_by'] {
  const user = db.users.find((candidate) => candidate.id === userId)
  return user ? { id: user.id, full_name: user.full_name ?? '', email: user.email } : null
}
