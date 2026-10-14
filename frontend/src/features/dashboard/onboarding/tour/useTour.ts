import { createContext, useContext } from 'react'

/**
 * The dashboard tour (docs/contracts/onboarding.md). Stub interface: the tour agent replaces the
 * implementation and keeps these exports.
 */
export type TourContextValue = {
  /** Starts the tour from its first step (also used to replay it). */
  start: () => void
  active: boolean
}

export const TourContext = createContext<TourContextValue | null>(null)

export function useTour(): TourContextValue {
  const context = useContext(TourContext)
  if (!context) throw new Error('useTour must be used inside <TourProvider>')
  return context
}
