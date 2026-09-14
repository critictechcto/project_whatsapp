import { StatusBadge, Tooltip } from '../../../../components/app'
import { reviewInfo } from '../lib/labels'
import type { Product } from '../lib/types'

/**
 * Meta review status. Rejection reasons show in a tooltip on hover or focus and are also part of
 * the badge's accessible text, so they never live only in the tooltip.
 */
export function ReviewBadge({ product }: { product: Pick<Product, 'meta_review_status' | 'meta_rejection_reasons'> }) {
  const info = reviewInfo[product.meta_review_status]
  const reasons = product.meta_review_status === 'rejected' ? product.meta_rejection_reasons : []
  const detail = reasons.length ? reasons.join(' ') : info.explanation
  return (
    <Tooltip
      content={
        reasons.length ? (
          <ul className="list-disc space-y-0.5 pl-3.5">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          info.explanation
        )
      }
    >
      <span tabIndex={0} className="rounded-full focus-visible:outline-2 focus-visible:outline-accent">
        <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
        <span className="sr-only">. {detail}</span>
      </span>
    </Tooltip>
  )
}
