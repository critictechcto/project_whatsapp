import { site } from '../../../../config/site'

/*
 * What the phones show in each chapter of the scroll story. Shared by the CSS fallback (DOM) and the
 * WebGL scene (drawn to canvas textures), so both tell the same story. Sample content only.
 */

/** Beats (sub-steps) per chapter. Each message appears at one beat of its chapter. */
export const storyBeats = [3, 3, 3, 3, 4] as const

export type StoryMessage = {
  chapter: number
  beat: number
  /** Relative to the phone's owner: `out` is sent from this phone (right, green). */
  side: 'in' | 'out'
  kind?: 'product' | 'address'
  title?: string
  lines?: string[]
  /** Label/amount rows, for the cart. */
  rows?: [string, string][]
  buttons?: string[]
  /** Label of the button shown as tapped. */
  pressed?: string
  time: string
}

export const buyerChat = { name: 'Sharma Sweets', subtitle: 'Business account', initials: 'SS', clock: '11:08' }
export const sellerChat = { name: `${site.name} Alerts`, subtitle: 'Order alerts', initials: 'UA', clock: '16:40' }

export const buyerMessages: StoryMessage[] = [
  {
    chapter: 0,
    beat: 0,
    side: 'in',
    title: 'Diwali mithai boxes are here',
    lines: ['Namaste Kabir! Fresh Kaju Katli and Soan Papdi, delivered across Jaipur.', 'Reply STOP to opt out.'],
    buttons: ['Shop now'],
    time: '11:00',
  },
  { chapter: 1, beat: 0, side: 'out', lines: ['Shop now'], time: '11:02' },
  {
    chapter: 1,
    beat: 1,
    side: 'in',
    lines: ['Welcome to Sharma Sweets! Pick a collection.'],
    buttons: ['View menu'],
    pressed: 'View menu',
    time: '11:02',
  },
  {
    chapter: 1,
    beat: 2,
    side: 'in',
    kind: 'product',
    title: 'Kaju Katli 250 g',
    lines: ['₹220 · made fresh every morning'],
    buttons: ['Add to cart', 'Next item'],
    pressed: 'Add to cart',
    time: '11:03',
  },
  {
    chapter: 2,
    beat: 0,
    side: 'in',
    title: 'Your cart · 3 items',
    rows: [
      ['2 × Kaju Katli 250 g', '₹440'],
      ['1 × Soan Papdi 250 g', '₹100'],
      ['Total', '₹540'],
    ],
    buttons: ['Checkout'],
    pressed: 'Checkout',
    time: '11:04',
  },
  {
    chapter: 2,
    beat: 1,
    side: 'in',
    lines: ['Where should we deliver your order?'],
    buttons: ['Provide address'],
    time: '11:04',
  },
  {
    chapter: 2,
    beat: 2,
    side: 'out',
    kind: 'address',
    title: 'Address shared',
    lines: ['C-12, Malviya Nagar, Jaipur 302017'],
    time: '11:05',
  },
  {
    chapter: 3,
    beat: 0,
    side: 'in',
    lines: ['How would you like to pay ₹540?'],
    buttons: ['Pay online', 'Cash on delivery'],
    pressed: 'Pay online',
    time: '11:05',
  },
  {
    chapter: 3,
    beat: 1,
    side: 'in',
    lines: ['Order SS-1042 · ₹540. Pay by UPI or card on Sharma Sweets’ payment page.'],
    buttons: ['Pay ₹540'],
    time: '11:05',
  },
  {
    chapter: 3,
    beat: 2,
    side: 'in',
    lines: ['Payment received, thank you! Order SS-1042 is confirmed.'],
    buttons: ['My orders'],
    time: '11:06',
  },
  {
    chapter: 4,
    beat: 3,
    side: 'in',
    lines: ['Order SS-1042 has shipped. We’ll message you when it is out for delivery.'],
    buttons: ['My orders'],
    time: '16:41',
  },
]

/** An older alert already in the seller's chat before the story's order arrives. */
export const sellerEarlier: StoryMessage = {
  chapter: 0,
  beat: 0,
  side: 'in',
  lines: ['SS-1039 delivered. Collect ₹860 cash on delivery from the courier.'],
  time: 'Yesterday',
}

export const sellerMessages: StoryMessage[] = [
  {
    chapter: 4,
    beat: 0,
    side: 'in',
    title: 'New order SS-1042 · ₹540',
    lines: ['Paid online · Kabir, Jaipur 302017', '2 × Kaju Katli, 1 × Soan Papdi'],
    buttons: ['Mark packed', 'Mark shipped'],
    time: '11:06',
  },
  { chapter: 4, beat: 1, side: 'out', lines: ['Mark shipped'], time: '16:40' },
  { chapter: 4, beat: 2, side: 'in', lines: ['SS-1042 marked shipped. The buyer has been notified.'], time: '16:40' },
]

/** Fraction of its chapter after which beat `beat` shows. Beat 0 shows almost as soon as the chapter starts. */
export function beatStart(beat: number, beats: number) {
  return (beat + 0.15) / beats
}

/** Beats of a chapter showing at chapter-local progress `local` (0..beats). */
export function visibleBeats(local: number, beats: number) {
  let count = 0
  while (count < beats && local >= beatStart(count, beats)) count++
  return count
}

/** Messages on screen in `chapter` with `beats` of it showing: earlier chapters stay in the history. */
export function messagesShown(messages: StoryMessage[], chapter: number, beats: number) {
  return messages.filter((message) => message.chapter < chapter || (message.chapter === chapter && message.beat < beats))
}

/** Where a message appears, in chapters elapsed (the `--story-u` scale). */
export function messageStart(message: StoryMessage) {
  return message.chapter + beatStart(message.beat, storyBeats[message.chapter])
}
