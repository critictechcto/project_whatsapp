import { Store } from 'lucide-react'
import { EmptyState, PageHeader } from '../../../components/app'

export function StorePage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Store"
        description="Set up selling on your WhatsApp number: store menus, shipping, payments and order alerts."
      />
      <EmptyState
        icon={<Store />}
        title="Your store isn't set up yet"
        description="Add products, choose how buyers pay (online through your own Razorpay account, or cash on delivery), then turn the store on."
      />
    </div>
  )
}
