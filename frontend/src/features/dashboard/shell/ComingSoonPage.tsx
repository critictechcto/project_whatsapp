import { Hammer } from 'lucide-react'
import { EmptyState, PageHeader } from '../../../components/app'

export function ComingSoonPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={title} description={description} />
      <EmptyState
        icon={<Hammer />}
        title="Coming soon"
        description={`${title} is being built. It will appear here in an upcoming release.`}
      />
    </div>
  )
}
