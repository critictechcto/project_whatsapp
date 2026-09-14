import { setupServer } from 'msw/node'
import { handlers } from './handlers'

/** MSW server for vitest. Override per test with `server.use(...)`. */
export const server = setupServer(...handlers)
