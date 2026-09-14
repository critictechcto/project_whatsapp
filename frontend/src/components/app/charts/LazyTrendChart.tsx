import { lazy, Suspense } from 'react'
import { Skeleton } from '../Spinner'
import type { TrendChartProps } from './TrendChart'

const TrendChart = lazy(() => import('./TrendChart'))

/** Loads recharts on first render (own `charts` chunk). */
export function LazyTrendChart(props: TrendChartProps) {
  return (
    <Suspense fallback={<Skeleton className="w-full" />}>
      <TrendChart {...props} />
    </Suspense>
  )
}
