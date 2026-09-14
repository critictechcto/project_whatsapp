import { Package } from 'lucide-react'
import { EmptyState, PageHeader } from '../../../components/app'

export function CatalogPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Catalog"
        description="Products you sell on WhatsApp. Buyers browse them in your store menus, or in WhatsApp's own catalog once you connect a Meta catalog."
      />
      <EmptyState
        icon={<Package />}
        title="No products yet"
        description="Add products with a name, price and photo. Prices are in rupees and include GST."
      />
    </div>
  )
}
