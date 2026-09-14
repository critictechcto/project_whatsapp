import type { Schemas } from '../../../../api/types'

export type Product = Schemas['Product']
export type ProductWriteRequest = Schemas['ProductWriteRequest']
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
