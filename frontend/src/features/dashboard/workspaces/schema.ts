import { z } from 'zod'
import { isKnownTimeZone } from './timeZones'

export const workspaceSchema = z.object({
  name: z.string().trim().min(2, 'Use at least 2 characters.').max(120, 'Use 120 characters or fewer.'),
  time_zone: z.string().refine(isKnownTimeZone, 'Choose a time zone from the list.'),
})

export type WorkspaceValues = z.infer<typeof workspaceSchema>
