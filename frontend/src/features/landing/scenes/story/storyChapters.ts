import { site } from '../../../../config/site'

/*
 * Copy for the "From first message to delivered order" scroll story. This module ships in the landing
 * entry chunk, so it holds only the text; what the phones show lives in `storyScreens.ts`, which is
 * loaded with the visuals.
 */

export type StoryChapter = {
  /** Short label for the progress rail. */
  label: string
  title: string
  body: string
  /** Small print under the body. */
  note?: string
}

export const storyChapters: StoryChapter[] = [
  {
    label: 'Campaign',
    title: 'An approved template reaches opted-in buyers',
    body: 'Sharma Sweets sends its Diwali offer to contacts who opted in, using a template Meta has approved. Sent, delivered and read statuses come back from Meta as they happen.',
    note: 'Read status appears only when the buyer has read receipts turned on.',
  },
  {
    label: 'Browse',
    title: 'The buyer taps Shop now and browses',
    body: 'The reply opens the shop inside the same chat. Product cards show the price and an Add to cart button, with no website or app to install.',
  },
  {
    label: 'Cart and address',
    title: 'A cart, then a delivery address',
    body: 'Items collect in a cart as the buyer taps. At checkout they send their address through WhatsApp’s address form, or simply type it.',
  },
  {
    label: 'Pay',
    title: 'Pay by link, or cash on delivery',
    body: `The payment link comes from the seller’s own Razorpay or Cashfree account, so the money goes straight to the seller. ${site.name} never holds it. Buyers can choose cash on delivery if the seller offers it.`,
  },
  {
    label: 'Seller alert',
    title: 'Marked shipped from the seller’s own WhatsApp',
    body: `The ${site.name} alerts number messages the seller’s personal WhatsApp about the new order. One tap on Mark shipped, and the buyer gets the shipped update in their chat.`,
  },
]

export const STORY_CHAPTER_COUNT = storyChapters.length
