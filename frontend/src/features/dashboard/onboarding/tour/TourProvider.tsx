import { useMemo, useState, type ReactNode } from 'react'
import { TourContext } from './useTour'

/** Hosts the tour for the shell. Stub: the tour agent implements the steps and popovers. */
export function TourProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState(false)
  const value = useMemo(() => ({ start: () => setActive(true), active }), [active])
  return <TourContext.Provider value={value}>{children}</TourContext.Provider>
}
