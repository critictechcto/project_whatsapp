import type { AreaMockHandlers } from '../registry/types'

/**
 * MSW handlers for the home area. Intentionally empty: home only reads list endpoints owned by other
 * areas (whatsapp, contacts, templates, inbox, campaigns, automations, team, billing), whose mocks
 * serve them. Handlers here would shadow those areas' mocks, because home's handlers are registered first.
 */
export const handlers: AreaMockHandlers = []
