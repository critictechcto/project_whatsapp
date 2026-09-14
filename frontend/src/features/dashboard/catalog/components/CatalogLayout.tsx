import type { ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { PageHeader, Tabs } from '../../../../components/app'
import { useWorkspace } from '../../../../lib/workspace'
import { useCatalogSyncRefresh } from '../api'

export type CatalogTab = 'products' | 'collections' | 'whatsapp'

const tabs: { value: CatalogTab; label: string; path: string }[] = [
  { value: 'products', label: 'Products', path: 'catalog' },
  { value: 'collections', label: 'Collections', path: 'catalog/collections' },
  { value: 'whatsapp', label: 'WhatsApp catalog', path: 'catalog/whatsapp' },
]

/** Page header and section tabs shared by the catalog screens. Also refetches on `catalog.sync`. */
export function CatalogLayout({ tab, actions, children }: { tab: CatalogTab; actions?: ReactNode; children: ReactNode }) {
  const { workspaceId } = useWorkspace()
  const navigate = useNavigate()
  useCatalogSyncRefresh()

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Catalog"
        description="Products you sell on WhatsApp. Buyers browse them in your store menus, or in WhatsApp's own catalog once you connect a Meta catalog."
        actions={actions}
      />
      <Tabs
        label="Catalog sections"
        items={tabs}
        value={tab}
        onValueChange={(value) => {
          const target = tabs.find((item) => item.value === value)
          if (target) navigate(`/app/w/${workspaceId}/${target.path}`)
        }}
      >
        <div className="flex flex-col gap-5">{children}</div>
      </Tabs>
    </div>
  )
}
