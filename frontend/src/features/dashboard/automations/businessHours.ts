import { z } from 'zod'
import type { BusinessHours, BusinessHoursSlot } from './api'

/** API days: 0 = Monday … 6 = Sunday. */
export const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const

export const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/
export const MAX_SLOTS = 50
export const defaultSlot = { start: '10:00', end: '19:00' } as const

const daySchema = z
  .object({ open: z.boolean(), slots: z.array(z.object({ start: z.string(), end: z.string() })) })
  .superRefine((day, ctx) => {
    if (!day.open) return
    if (!day.slots.length) ctx.addIssue({ code: 'custom', path: ['slots'], message: 'Add opening hours or mark the day closed.' })
    day.slots.forEach((slot, index) => {
      if (!TIME_PATTERN.test(slot.start)) ctx.addIssue({ code: 'custom', path: ['slots', index, 'start'], message: 'Enter an opening time.' })
      if (!TIME_PATTERN.test(slot.end)) ctx.addIssue({ code: 'custom', path: ['slots', index, 'end'], message: 'Enter a closing time.' })
      else if (slot.start === slot.end) {
        ctx.addIssue({ code: 'custom', path: ['slots', index, 'end'], message: "Opening and closing times can't be the same." })
      }
    })
  })

export const businessHoursSchema = z
  .object({ enabled: z.boolean(), days: z.array(daySchema).length(7) })
  .superRefine((value, ctx) => {
    const total = value.days.reduce((sum, day) => sum + (day.open ? day.slots.length : 0), 0)
    if (total > MAX_SLOTS) ctx.addIssue({ code: 'custom', path: ['enabled'], message: `Use ${MAX_SLOTS} time slots or fewer in a week.` })
  })

export type BusinessHoursFormValues = z.infer<typeof businessHoursSchema>
export type DayFormValues = BusinessHoursFormValues['days'][number]

export function hoursToForm(hours: Pick<BusinessHours, 'enabled' | 'schedule'>): BusinessHoursFormValues {
  return {
    enabled: hours.enabled,
    days: dayNames.map((_, day) => {
      const slots = hours.schedule.filter((slot) => slot.day === day).map(({ start, end }) => ({ start, end }))
      return { open: slots.length > 0, slots }
    }),
  }
}

export function formToSchedule(values: BusinessHoursFormValues): BusinessHoursSlot[] {
  return values.days.flatMap((day, index) => (day.open ? day.slots.map((slot) => ({ day: index, start: slot.start, end: slot.end })) : []))
}

/** A closing time earlier than the opening time runs past midnight. */
export function isOvernight(slot: { start: string; end: string }): boolean {
  return TIME_PATTERN.test(slot.start) && TIME_PATTERN.test(slot.end) && slot.end < slot.start
}
