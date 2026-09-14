import type { Schemas } from '../../../api/types'
import { db, type Mutable } from '../../../mocks/db'
import { ids, seedPhoneNumber, seedWaba } from '../../../mocks/seed'

/**
 * In-memory WhatsApp accounts and numbers for the mock API. Rebuilt whenever the mock database
 * is reset (detected by `db.users` changing identity), so tests start from the seed.
 */

export type MockAccount = Mutable<Omit<Schemas['WhatsAppBusinessAccount'], 'phone_numbers'>> & { workspace_id: string }
export type MockPhoneNumber = Mutable<Schemas['PhoneNumber']> & { workspace_id: string }
type WhatsAppState = { accounts: MockAccount[]; numbers: MockPhoneNumber[] }

function build(): WhatsAppState {
  return {
    accounts: [{ ...seedWaba, workspace_id: ids.sharmaSweets }],
    numbers: [{ ...seedPhoneNumber, workspace_id: ids.sharmaSweets }],
  }
}

let snapshot: unknown = null
let state: WhatsAppState = build()

export function whatsappState(): WhatsAppState {
  if (snapshot !== db.users) {
    snapshot = db.users
    state = build()
  }
  return state
}

export function phoneNumbersFor(workspaceId: string): MockPhoneNumber[] {
  return whatsappState().numbers.filter((number) => number.workspace_id === workspaceId)
}
