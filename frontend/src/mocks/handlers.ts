import type { HttpHandler } from 'msw'
import { areaMockHandlers } from '../features/dashboard/registry/mocks'
import { authHandlers } from './handlers/auth'
import { sharedHandlers } from './handlers/shared'
import { workspaceHandlers } from './handlers/workspaces'

/**
 * Area handlers come first so a feature area can override a shared fallback
 * (e.g. the templates area replacing the basic template list used by `TemplatePicker`).
 */
export const handlers: HttpHandler[] = [...areaMockHandlers, ...authHandlers, ...workspaceHandlers, ...sharedHandlers]
