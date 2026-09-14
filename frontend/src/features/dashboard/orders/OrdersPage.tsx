import { ShoppingBag } from 'lucide-react'
import { EmptyState, PageHeader } from '../../../components/app'

export function OrdersPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Orders"
        description="Orders your buyers place on WhatsApp. Mark them packed, shipped and delivered here; each change notifies the buyer."
      />
      <EmptyState
        icon={<ShoppingBag />}
        title="No orders yet"
        description="Orders appear here when buyers check out, whether they pay online or choose cash on delivery."
      />
    </div>
  )
}
