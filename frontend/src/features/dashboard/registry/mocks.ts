/**
 * Mock handlers of every area. Imported only by `src/mocks/handlers.ts`, which loads in mock
 * builds and tests, so none of this ships in a live build.
 */
import type { HttpHandler } from 'msw'
import { handlers as automations } from '../automations/mocks'
import { handlers as billing } from '../billing/mocks'
import { handlers as campaigns } from '../campaigns/mocks'
import { handlers as contacts } from '../contacts/mocks'
import { handlers as home } from '../home/mocks'
import { handlers as inbox } from '../inbox/mocks'
import { handlers as settings } from '../settings/mocks'
import { handlers as team } from '../team/mocks'
import { handlers as templates } from '../templates/mocks'
import { handlers as whatsapp } from '../whatsapp/mocks'

export const areaMockHandlers: HttpHandler[] = [
  ...home,
  ...inbox,
  ...contacts,
  ...campaigns,
  ...templates,
  ...automations,
  ...whatsapp,
  ...team,
  ...billing,
  ...settings,
]
