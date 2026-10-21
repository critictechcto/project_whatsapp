import type { Tone } from '../../../../components/app'
import { formatPaise } from '../../../../lib/money'
import type { BookingPayment, CatalogSyncStatus, MetaCatalogStatus, MetaReviewStatus, Product, ProductAvailability } from './types'

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

/** Services use the same values, worded as bookings. */
export const bookingAvailabilityLabels: Record<ProductAvailability, string> = {
  in_stock: 'Open',
  out_of_stock: 'Paused',
}

export const bookingPaymentLabels: Record<BookingPayment, string> = {
  store_default: 'Use store setting',
  advance: 'Advance payment',
  full: 'Full payment',
}

/** "Advance ₹200", "Advance 20%" or "Full payment" for a service that sets it; null otherwise. */
export function bookingPaymentSummary(product: Pick<Product, 'kind' | 'booking_payment' | 'advance_type' | 'advance_value'>): string | null {
  if (product.kind !== 'service') return null
  if (product.booking_payment === 'full') return 'Full payment'
  if (product.booking_payment !== 'advance' || product.advance_value == null) return null
  return product.advance_type === 'amount' ? `Advance ${formatPaise(product.advance_value)}` : `Advance ${product.advance_value}%`
}
