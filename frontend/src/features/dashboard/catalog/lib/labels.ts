import type { Tone } from '../../../../components/app'
import type { CatalogSyncStatus, MetaCatalogStatus, MetaReviewStatus, ProductAvailability } from './types'

type Info = { label: string; tone: Tone; explanation: string }

export const reviewInfo: Record<MetaReviewStatus, Info> = {
  none: { label: 'Not reviewed', tone: 'neutral', explanation: 'Not sent to Meta yet. Products need a photo to sync.' },
  pending: { label: 'In review', tone: 'amber', explanation: 'Meta is reviewing this product.' },
  approved: { label: 'Approved', tone: 'green', explanation: 'Meta approved this product for your WhatsApp catalog.' },
  rejected: { label: 'Rejected', tone: 'red', explanation: 'Meta rejected this product.' },
  outdated: { label: 'Changes pending', tone: 'blue', explanation: 'Recent changes are waiting to reach Meta.' },
}

export const syncInfo: Record<CatalogSyncStatus, { label: string; tone: Tone }> = {
  not_synced: { label: 'Not synced', tone: 'neutral' },
  pending: { label: 'Syncing', tone: 'blue' },
  synced: { label: 'Synced', tone: 'green' },
  failed: { label: 'Sync failed', tone: 'red' },
}

export const catalogStatusInfo: Record<MetaCatalogStatus, { label: string; tone: Tone }> = {
  connected: { label: 'Connected', tone: 'green' },
  permissions_missing: { label: 'Permissions missing', tone: 'red' },
  error: { label: 'Error', tone: 'red' },
}

export const availabilityLabels: Record<ProductAvailability, string> = {
  in_stock: 'In stock',
  out_of_stock: 'Out of stock',
}
