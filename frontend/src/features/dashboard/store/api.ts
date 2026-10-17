import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { workspaceKeys } from '../../../api/queryKeys'
import type { Schemas } from '../../../api/types'

export type StoreSettings = Schemas['StoreSettings']
export type StoreSettingsPatch = Schemas['PatchedStoreSettingsRequest']
/** A booking time window, `HH:MM` in the workspace time zone. */
export type BookingWindow = Schemas['BookingWindow']
export type BookingTemplateField = 'booking_confirmed_template_id' | 'booking_cancelled_template_id' | 'booking_reminder_template_id'

export const DEFAULT_BOOKING_WINDOWS: readonly BookingWindow[] = [
  { label: 'Morning', start: '09:00', end: '12:00' },
  { label: 'Afternoon', start: '12:00', end: '16:00' },
  { label: 'Evening', start: '16:00', end: '20:00' },
]

export type StoreChecklistItem = Schemas['StoreChecklistItem']
export type PaymentAccount = Schemas['PaymentAccount']
export type PaymentAccountPatch = Schemas['PatchedPaymentAccountRequest']
export type PaymentProvider = Schemas['PaymentProviderEnum']
export type PaymentMode = Schemas['PaymentModeEnum']
export type PaymentAccountStatus = Schemas['PaymentAccountStatusEnum']
export type AlertRecipient = Schemas['AlertRecipient']
export type AlertEvent = Schemas['AlertEventEnum']
export type AlertRecipientStatus = Schemas['AlertRecipientStatusEnum']
export type NotificationKey = keyof Schemas['OrderNotificationTemplates']

/** Query keys: `['ws', workspaceId, 'store', ...]`. */
export const storeKeys = workspaceKeys('store')

export const storeQueryKeys = {
  settings: (workspaceId: string) => storeKeys.custom(workspaceId, 'settings'),
  checklist: (workspaceId: string) => storeKeys.custom(workspaceId, 'checklist'),
  payments: (workspaceId: string) => storeKeys.custom(workspaceId, 'payments'),
  platform: (workspaceId: string) => storeKeys.custom(workspaceId, 'alerts-platform'),
  recipients: (workspaceId: string) => storeKeys.custom(workspaceId, 'alerts-recipients'),
  phoneNumbers: (workspaceId: string) => storeKeys.custom(workspaceId, 'phone-numbers'),
}

export function fetchStoreSettings(signal?: AbortSignal): Promise<StoreSettings> {
  return unwrap(api.GET('/api/v1/store/settings/', { signal }))
}

export function patchStoreSettings(body: StoreSettingsPatch): Promise<StoreSettings> {
  return unwrap(api.PATCH('/api/v1/store/settings/', { body }))
}

export function useStoreSettings(workspaceId: string) {
  return useQuery({
    queryKey: storeQueryKeys.settings(workspaceId),
    queryFn: ({ signal }) => fetchStoreSettings(signal),
  })
}

/** Caches the whole response: the home store card shares this query key. */
export function useStoreChecklist(workspaceId: string) {
  return useQuery({
    queryKey: storeQueryKeys.checklist(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/store/checklist/', { signal })),
  })
}

export function usePaymentAccount(workspaceId: string) {
  return useQuery({
    queryKey: storeQueryKeys.payments(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/payments/account/', { signal })),
  })
}

export function usePlatformAlerts(workspaceId: string) {
  return useQuery({
    queryKey: storeQueryKeys.platform(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/seller-alerts/platform/', { signal })),
    staleTime: 5 * 60_000,
  })
}

export function useAlertRecipients(workspaceId: string) {
  return useQuery({
    queryKey: storeQueryKeys.recipients(workspaceId),
    queryFn: async ({ signal }) =>
      (await unwrap(api.GET('/api/v1/seller-alerts/recipients/', { params: { query: { page_size: 50 } }, signal }))).results,
  })
}

/** The workspace's WhatsApp numbers, for the store number select. */
export function useStorePhoneNumbers(workspaceId: string) {
  return useQuery({
    queryKey: storeQueryKeys.phoneNumbers(workspaceId),
    queryFn: async ({ signal }) =>
      (await unwrap(api.GET('/api/v1/whatsapp/phone-numbers/', { params: { query: { page_size: 50 } }, signal }))).results,
    staleTime: 60_000,
  })
}
