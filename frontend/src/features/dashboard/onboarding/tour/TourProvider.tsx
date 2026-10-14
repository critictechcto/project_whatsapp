import { lazy, Suspense, useCallback, useMemo, useState, type ReactNode } from 'react'
import { useUpdateOnboarding } from '../api'
import { TourContext } from './useTour'

// The popover UI loads on the first start(), so the shell chunk only carries this provider.
const TourOverlay = lazy(() => import('./TourOverlay'))

/** Hosts the tour for the shell: `start()` (re)opens it at step 1; finishing or skipping records it. */
export function TourProvider({ children }: { children: ReactNode }) {
  // Each start bumps the run, which remounts the overlay at its first step.
  const [run, setRun] = useState(0)
  const [active, setActive] = useState(false)
  const { mutate } = useUpdateOnboarding()

  const start = useCallback(() => {
    setRun((value) => value + 1)
    setActive(true)
  }, [])

  const finish = useCallback(() => {
    setActive(false)
    mutate({ tour_completed: true })
  }, [mutate])

  const value = useMemo(() => ({ start, active }), [start, active])

  return (
    <TourContext.Provider value={value}>
      {children}
      {active && (
        <Suspense fallback={null}>
          <TourOverlay key={run} onFinish={finish} />
        </Suspense>
      )}
    </TourContext.Provider>
  )
}
