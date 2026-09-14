import type { AreaRoute } from '../registry/types'

/** Placeholder route for an area that isn't built yet. Replace with your real routes. */
export function comingSoonRoute(path: string, title: string, description: string): AreaRoute {
  return {
    path,
    handle: { title },
    lazy: async () => {
      const { ComingSoonPage } = await import('./ComingSoonPage')
      return { element: <ComingSoonPage title={title} description={description} /> }
    },
  }
}
