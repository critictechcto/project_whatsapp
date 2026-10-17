import type { Schemas } from '../../../../api/types'

export type ProductKind = 'product' | 'service'

/**
 * TODO(api:types): `kind` and `duration_minutes` come from the services contract
 * (`docs/contracts/services-and-offers.md`) and aren't in `schema.d.ts` yet. After `npm run api:types`
 * these become plain `Schemas[...]` aliases and the casts in `api.ts` can go.
 */
type ServiceFields = {
  readonly kind: ProductKind
  /** Services only, 5–600; null for products. */
  readonly duration_minutes: number | null
}

export type Product = Schemas['Product'] & ServiceFields
export type ProductWriteRequest = Schemas['ProductWriteRequest'] & { kind?: ProductKind; duration_minutes?: number | null }
export type Collection = Schemas['Collection']
export type MetaCatalog = Schemas['MetaCatalog']
export type AvailableCatalog = Schemas['AvailableCatalog']
export type CommerceSettings = Schemas['CommerceSettings']
export type ProductImportResult = Schemas['ProductImportResult']
export type ProductAvailability = Schemas['ProductAvailabilityEnum']
export type MetaReviewStatus = Schemas['MetaReviewStatusEnum']
export type CatalogSyncStatus = Schemas['CatalogSyncStatusEnum']
export type MetaCatalogStatus = Schemas['MetaCatalogStatusEnum']
export type WhatsAppAccount = Schemas['WhatsAppBusinessAccount']

export const availabilityValues = ['in_stock', 'out_of_stock'] as const satisfies readonly ProductAvailability[]
export const reviewValues = ['none', 'pending', 'approved', 'rejected', 'outdated'] as const satisfies readonly MetaReviewStatus[]
export const productKindValues = ['product', 'service'] as const satisfies readonly ProductKind[]
