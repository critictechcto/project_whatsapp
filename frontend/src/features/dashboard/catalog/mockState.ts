/**
 * In-memory catalog data for the mock API (mock mode and tests): Sharma Sweets with 3 collections,
 * 12 products (one rejected in Meta review, one out of stock) and a connected Meta catalog.
 * Rebuilt whenever the shared mock database is reset (`db.users` changes identity).
 */
import type { Schemas } from '../../../api/types'
import { db, type Mutable } from '../../../mocks/db'
import { daysAgo, ids, seedPhoneNumber, seedWaba } from '../../../mocks/seed'

export type MockCollection = Omit<Mutable<Schemas['Collection']>, 'product_count'> & { workspace_id: string }
export type MockProduct = Omit<Mutable<Schemas['Product']>, 'collection' | 'effective_price_paise' | 'meta_rejection_reasons'> & {
  workspace_id: string
  collection_id: string | null
  meta_rejection_reasons: string[]
}
export type MockMetaCatalog = Omit<Mutable<Schemas['MetaCatalog']>, 'product_counts' | 'phone_numbers'> & {
  workspace_id: string
  phone_numbers: Array<Mutable<Schemas['CommerceSettings']>>
}

export type CatalogMockState = {
  collections: MockCollection[]
  products: MockProduct[]
  metaCatalogs: MockMetaCatalog[]
  /** Catalogs in the seller's Meta business, by WABA uuid. */
  availableCatalogs: Record<string, Schemas['AvailableCatalog'][]>
  /** When true, available/connect answer 409 `catalog_permissions_missing` (tests and demo tweaks). */
  permissionsMissing: boolean
}

const pad = (n: number) => String(n).padStart(12, '0')
export const collectionId = (n: number) => `b7c1d2e3-4f5a-4b6c-8d7e-${pad(n)}`
export const productId = (n: number) => `c8d2e3f4-5a6b-4c7d-9e8f-${pad(n)}`
export const metaCatalogId = 'd9e3f4a5-6b7c-4d8e-8f90-000000000001'

/** A square SVG tile standing in for a product photo, so mock mode needs no network. */
export function mockProductImage(label: string, hue = 32): string {
  const initials = label
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600"><rect width="600" height="600" fill="hsl(${hue} 55% 86%)"/><circle cx="300" cy="300" r="170" fill="hsl(${hue} 45% 72%)"/><text x="300" y="340" font-family="Georgia, serif" font-size="120" text-anchor="middle" fill="hsl(${hue} 40% 28%)">${initials}</text></svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

type Seed = {
  sku: string
  name: string
  description: string
  price: number
  sale?: number
  collection: number | null
  stock?: number | null
  availability?: Schemas['ProductAvailabilityEnum']
  active?: boolean
  image?: boolean
  review?: Schemas['MetaReviewStatusEnum']
  reasons?: string[]
  hue: number
}

const seeds: Seed[] = [
  { sku: 'KAJU-KATLI-500', name: 'Kaju katli 500 g', description: 'Silver-leaf kaju katli made with pure desi ghee.', price: 65000, sale: 59900, collection: 1, stock: 40, review: 'approved', hue: 38 },
  { sku: 'KAJU-KATLI-1KG', name: 'Kaju katli 1 kg', description: 'Our bestseller in a family-size box.', price: 125000, collection: 1, review: 'approved', hue: 40 },
  { sku: 'BADAM-BARFI-500', name: 'Badam barfi 500 g', description: 'Almond barfi with saffron and cardamom.', price: 72000, collection: 1, stock: 12, review: 'approved', hue: 28 },
  { sku: 'PISTA-ROLL-250', name: 'Pista roll 250 g', description: 'Pistachio rolls wrapped in kaju dough.', price: 48000, collection: 1, stock: 0, availability: 'out_of_stock', review: 'approved', hue: 95 },
  {
    sku: 'ANJEER-BARFI-SF',
    name: 'Sugar-free anjeer barfi 400 g',
    description: 'Fig barfi sweetened only with dates. Good for diabetics.',
    price: 68000,
    collection: 1,
    stock: 15,
    review: 'rejected',
    reasons: ['Health claims such as "good for diabetics" aren’t allowed in product descriptions.', 'The image contains promotional text.'],
    hue: 20,
  },
  { sku: 'MOTICHOOR-LADDU-1KG', name: 'Motichoor laddu 1 kg', description: 'Fresh boondi laddus fried in ghee every morning.', price: 56000, collection: 2, stock: 25, review: 'approved', hue: 30 },
  { sku: 'BESAN-LADDU-500', name: 'Besan laddu 500 g', description: 'Slow-roasted gram flour laddus.', price: 32000, collection: 2, review: 'pending', hue: 42 },
  { sku: 'BOONDI-LADDU-500', name: 'Boondi laddu 500 g', description: 'Temple-style boondi laddus.', price: 28000, collection: 2, review: 'approved', hue: 45 },
  { sku: 'BIKANERI-BHUJIA-400', name: 'Bikaneri bhujia 400 g', description: 'Crunchy moth-bean bhujia from Bikaner.', price: 18000, collection: 3, stock: 60, review: 'approved', hue: 48 },
  { sku: 'METHI-MATHRI-250', name: 'Methi mathri 250 g', description: 'Flaky fenugreek mathri, perfect with chai.', price: 15000, sale: 13000, collection: 3, review: 'approved', hue: 70 },
  { sku: 'DIWALI-HAMPER-L', name: 'Diwali gift hamper (large)', description: 'Kaju katli, soan papdi, dry fruits and diyas in a gift box.', price: 249900, collection: 3, stock: 8, image: false, review: 'none', hue: 10 },
  { sku: 'MALAI-GHEWAR-4', name: 'Malai ghewar (4 pcs)', description: 'Seasonal Jaipur ghewar topped with rabri. Available in Sawan.', price: 54000, collection: null, active: false, review: 'approved', hue: 35 },
]

function build(): CatalogMockState {
  const workspace_id = ids.sharmaSweets
  const collections: MockCollection[] = [
    { id: collectionId(1), name: 'Dry fruit sweets', description: 'Kaju katli, badam barfi and pista rolls', position: 0, is_active: true, created_at: daysAgo(80), updated_at: daysAgo(10), workspace_id },
    { id: collectionId(2), name: 'Laddus', description: 'Motichoor, besan and boondi, made fresh daily', position: 1, is_active: true, created_at: daysAgo(80), updated_at: daysAgo(12), workspace_id },
    { id: collectionId(3), name: 'Namkeen & gift boxes', description: 'Bhujia, mathri and festive hampers', position: 2, is_active: true, created_at: daysAgo(70), updated_at: daysAgo(5), workspace_id },
  ]
  const products: MockProduct[] = seeds.map((seed, index) => {
    const image = seed.image ?? true
    const review = seed.review ?? 'none'
    return {
      id: productId(index + 1),
      workspace_id,
      sku: seed.sku,
      name: seed.name,
      description: seed.description,
      price_paise: seed.price,
      sale_price_paise: seed.sale ?? null,
      currency: 'INR',
      image_url: image ? mockProductImage(seed.name, seed.hue) : null,
      collection_id: seed.collection ? collectionId(seed.collection) : null,
      availability: seed.availability ?? 'in_stock',
      stock_qty: seed.stock ?? null,
      max_qty_per_order: 10,
      position: index,
      is_active: seed.active ?? true,
      meta_sync_status: image ? 'synced' : 'not_synced',
      meta_review_status: review,
      meta_rejection_reasons: seed.reasons ?? [],
      created_at: daysAgo(75 - index),
      updated_at: daysAgo(index % 6),
    }
  })
  const metaCatalogs: MockMetaCatalog[] = [
    {
      id: metaCatalogId,
      workspace_id,
      waba: { id: seedWaba.id, waba_id: seedWaba.waba_id, name: seedWaba.name },
      catalog_id: '873465019283746',
      catalog_name: 'Sharma Sweets products',
      status: 'connected',
      last_synced_at: daysAgo(0.05),
      last_sync_error: '',
      phone_numbers: [
        { phone_number_id: seedPhoneNumber.id, display_phone_number: seedPhoneNumber.display_phone_number, is_cart_enabled: true, is_catalog_visible: true },
      ],
      created_at: daysAgo(30),
      updated_at: daysAgo(0.05),
    },
  ]
  return {
    collections,
    products,
    metaCatalogs,
    availableCatalogs: {
      [seedWaba.id]: [
        { id: '873465019283746', name: 'Sharma Sweets products' },
        { id: '912837465019284', name: 'Sharma Sweets wholesale' },
      ],
    },
    permissionsMissing: false,
  }
}

let snapshot: unknown = null
let state: CatalogMockState = build()

export function catalogMock(): CatalogMockState {
  if (snapshot !== db.users) {
    snapshot = db.users
    state = build()
  }
  return state
}
