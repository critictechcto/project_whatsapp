import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { Link } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm, errorMessage, isApiError } from '../../../api/errors'
import {
  Button,
  Field,
  Input,
  InteractiveMessagePreview,
  PageSpinner,
  Select,
  StatusBadge,
  Switch,
  Textarea,
  useToast,
  type InteractiveButtonMessage,
} from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { KeywordChipsInput } from '../automations/components/KeywordChipsInput'
import { RadioCards } from '../campaigns/components/RadioCards'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { storeQueryKeys, useStorePhoneNumbers, useStoreSettings, type StoreSettings } from './api'
import { StoreFrame } from './components/StoreNav'
import { formToPatch, MAX_MENU_KEYWORDS, PINCODE, settingsFieldMap, settingsSchema, settingsToForm, type SettingsFormValues } from './settingsForm'

const DESCRIPTION = 'How your store greets buyers, what orders cost and where you deliver.'

export function StoreSettingsPage() {
  const { workspaceId } = useWorkspace()
  const settings = useStoreSettings(workspaceId)

  return (
    <StoreFrame description={DESCRIPTION}>
      {settings.isPending ? (
        <PageSpinner />
      ) : settings.isError ? (
        <Notice
          tone="danger"
          role="alert"
          title="Couldn't load store settings"
          action={
            <Button variant="secondary" size="sm" onClick={() => void settings.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(settings.error)}
        </Notice>
      ) : (
        <>
          <StoreStatusCard settings={settings.data} />
          <SettingsForm settings={settings.data} />
        </>
      )}
    </StoreFrame>
  )
}

function StoreStatusCard({ settings }: { settings: StoreSettings }) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const enabled = Boolean(settings.enabled)

  const toggle = useMutation({
    mutationFn: (next: boolean) => unwrap(api.PATCH('/api/v1/store/settings/', { body: { enabled: next } })),
    onSuccess: (saved) => {
      queryClient.setQueryData(storeQueryKeys.settings(workspaceId), saved)
      void queryClient.invalidateQueries({ queryKey: storeQueryKeys.checklist(workspaceId) })
      toast({ title: saved.enabled ? 'Your store is on' : 'Your store is off', tone: 'success' })
    },
  })

  const error = toggle.error
  return (
    <SectionCard
      id="store-status"
      title="Store status"
      actions={<StatusBadge tone={enabled ? 'green' : 'neutral'}>{enabled ? 'On' : 'Off'}</StatusBadge>}
    >
      <div className="flex flex-col gap-3">
        <Switch
          checked={enabled}
          disabled={toggle.isPending}
          onCheckedChange={(next) => toggle.mutate(next)}
          label="Store is on"
          description={
            enabled
              ? 'Buyers who send a menu keyword get your store menu.'
              : 'While the store is off, messages reach your inbox as usual and no store menu is sent.'
          }
        />
        {error && (
          <Notice tone="danger" role="alert" title={isApiError(error, 'commerce_not_enabled') ? "The store can't be turned on yet" : "Couldn't change the store status"}>
            {errorMessage(error)}
          </Notice>
        )}
      </div>
    </SectionCard>
  )
}

/** The welcome menu as buyers see it. */
function WelcomePreview({ message, poweredBy }: { message: string; poweredBy: boolean }) {
  const preview: InteractiveButtonMessage = {
    type: 'button',
    body: { text: message.trim() || 'Your welcome message appears here.' },
    ...(poweredBy ? { footer: { text: 'Powered by UpChatz' } } : {}),
    action: {
      buttons: [
        { type: 'reply', reply: { id: 'shop', title: 'Shop now' } },
        { type: 'reply', reply: { id: 'orders', title: 'My orders' } },
        { type: 'reply', reply: { id: 'support', title: 'Talk to us' } },
      ],
    },
  }
  return (
    <div role="group" aria-label="Welcome menu preview" className="flex flex-col gap-1.5">
      <p className="text-[13px] font-medium text-ink">Preview</p>
      <InteractiveMessagePreview message={preview} />
    </div>
  )
}

function MoneyField({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: React.ReactNode }) {
  return (
    <Field label={label} hint={hint} error={error}>
      {children}
    </Field>
  )
}

function SettingsForm({ settings }: { settings: StoreSettings }) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const phones = useStorePhoneNumbers(workspaceId)
  const [initialValues] = useState(() => settingsToForm(settings))
  const {
    control,
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<SettingsFormValues>({ resolver: zodResolver(settingsSchema), defaultValues: initialValues })

  const welcome = useWatch({ control, name: 'welcome_message' })
  const poweredBy = useWatch({ control, name: 'powered_by_footer' })
  const codEnabled = useWatch({ control, name: 'cod_enabled' })
  const money = (name: 'min_order' | 'shipping_fee' | 'free_shipping_above' | 'cod_fee' | 'cod_max_order', placeholder?: string) => (
    <Input {...register(name)} prefix="₹" inputMode="decimal" autoComplete="off" placeholder={placeholder} className="max-w-48" />
  )

  const onSubmit = handleSubmit(async (values) => {
    try {
      const saved = await unwrap(api.PATCH('/api/v1/store/settings/', { body: formToPatch(values) }))
      queryClient.setQueryData(storeQueryKeys.settings(workspaceId), saved)
      void queryClient.invalidateQueries({ queryKey: storeQueryKeys.checklist(workspaceId) })
      reset(settingsToForm(saved))
      toast({ title: 'Store settings saved', tone: 'success' })
    } catch (error) {
      if (isApiError(error, 'catalog_not_connected')) {
        setError('shop_mode', { type: 'server', message: error.message }, { shouldFocus: true })
        return
      }
      applyApiErrorToForm(error, setError, { fieldMap: settingsFieldMap, fields: Object.keys(initialValues) })
    }
  })

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-6">
      <SectionCard id="store-basics" title="Basics">
        <div className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Store name" error={errors.store_name?.message} required>
              <Input {...register('store_name')} maxLength={60} autoComplete="off" />
            </Field>
            <Field label="Store number" hint="The WhatsApp number buyers shop on." error={errors.phone_number_id?.message}>
              <Select
                {...register('phone_number_id')}
                options={[
                  { value: '', label: 'Workspace default number' },
                  ...(phones.data ?? []).map((phone) => ({ value: phone.id, label: `${phone.display_phone_number} · ${phone.verified_name}` })),
                ]}
              />
            </Field>
          </div>
          <Controller
            control={control}
            name="shop_mode"
            render={({ field }) => (
              <RadioCards
                legend="How buyers shop"
                value={field.value}
                onChange={field.onChange}
                error={errors.shop_mode?.message}
                options={[
                  {
                    value: 'bot',
                    label: 'Menus in the chat',
                    description: 'Buyers pick collections and products from menus, and the cart is kept for them. Works for every store.',
                  },
                  {
                    value: 'native_catalog',
                    label: 'WhatsApp catalog',
                    description: "Buyers browse WhatsApp's own catalog and send their cart. Needs a Meta catalog connected on the Catalog page.",
                  },
                ]}
              />
            )}
          />
          <Field label="Order number prefix" hint="2 to 5 capital letters. Orders are numbered like SS-1001." error={errors.order_prefix?.message} required>
            <Input
              {...register('order_prefix', { setValueAs: (value: string) => value.toUpperCase() })}
              maxLength={5}
              autoComplete="off"
              className="max-w-32 font-mono uppercase"
            />
          </Field>
        </div>
      </SectionCard>

      <SectionCard id="store-welcome" title="Welcome menu" description="Sent when a buyer messages one of your menu keywords.">
        <div className="flex flex-col gap-5">
          <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_280px]">
            <div className="flex flex-col gap-5">
              <Field label="Welcome message" hint="WhatsApp formatting works: *bold*, _italic_." error={errors.welcome_message?.message} required>
                <Textarea rows={5} maxLength={1024} {...register('welcome_message')} />
              </Field>
              <Controller
                control={control}
                name="powered_by_footer"
                render={({ field }) => (
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    label="Show “Powered by UpChatz”"
                    description="A small footer under the welcome menu."
                  />
                )}
              />
            </div>
            <WelcomePreview message={welcome} poweredBy={poweredBy} />
          </div>
          <Controller
            control={control}
            name="menu_keywords"
            render={({ field }) => (
              <KeywordChipsInput
                label="Menu keywords"
                value={field.value}
                onChange={field.onChange}
                error={errors.menu_keywords?.message}
                hint={`A message that is exactly one of these words (any case) opens the menu. Up to ${MAX_MENU_KEYWORDS}.`}
                normalize={(entry) => entry.toLowerCase()}
                max={MAX_MENU_KEYWORDS}
                placeholder="menu"
                required
              />
            )}
          />
          <Field label="Talk to us reply" hint="Sent when a buyer taps Talk to us. The chat then waits in your inbox." error={errors.support_message?.message} required>
            <Textarea rows={3} maxLength={1024} {...register('support_message')} />
          </Field>
        </div>
      </SectionCard>

      <SectionCard id="store-delivery" title="Orders and delivery" description="Amounts include GST.">
        <div className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <MoneyField label="Minimum order" hint="0 for no minimum." error={errors.min_order?.message}>
              {money('min_order')}
            </MoneyField>
            <MoneyField label="Shipping fee" hint="0 for free shipping." error={errors.shipping_fee?.message}>
              {money('shipping_fee')}
            </MoneyField>
            <MoneyField label="Free shipping above" hint="Leave empty to always charge shipping." error={errors.free_shipping_above?.message}>
              {money('free_shipping_above', 'Optional')}
            </MoneyField>
          </div>
          <Controller
            control={control}
            name="serviceable_pincodes"
            render={({ field }) => (
              <KeywordChipsInput
                label="Delivery pincodes"
                itemName="pincode"
                value={field.value}
                onChange={field.onChange}
                error={errors.serviceable_pincodes?.message}
                hint="Leave empty to deliver everywhere. Buyers outside these pincodes can't place an order."
                validate={(entry) => (PINCODE.test(entry) ? null : `“${entry}” isn't a 6-digit pincode.`)}
                placeholder="302001"
                inputMode="numeric"
                max={1000}
              />
            )}
          />
        </div>
      </SectionCard>

      <SectionCard id="store-cod" title="Cash on delivery">
        <div className="flex flex-col gap-5">
          <Controller
            control={control}
            name="cod_enabled"
            render={({ field }) => (
              <Switch
                checked={field.value}
                onCheckedChange={field.onChange}
                label="Offer cash on delivery"
                description="Buyers can choose to pay when the order arrives. You mark it collected on the order."
              />
            )}
          />
          {codEnabled && (
            <div className="grid gap-4 sm:grid-cols-2">
              <MoneyField label="COD fee" hint="Added to cash-on-delivery orders. 0 for none." error={errors.cod_fee?.message}>
                {money('cod_fee')}
              </MoneyField>
              <MoneyField label="Maximum COD order" hint="Larger orders must pay online. Leave empty for no limit." error={errors.cod_max_order?.message}>
                {money('cod_max_order', 'Optional')}
              </MoneyField>
            </div>
          )}
          <p className="text-[13px] text-muted">
            Online payments go through your own gateway.{' '}
            <Link to={`/app/w/${workspaceId}/store/payments`} className="text-accent-2 underline underline-offset-4">
              Payment settings
            </Link>
          </p>
        </div>
      </SectionCard>

      {errors.root?.server?.message && (
        <Notice tone="danger" role="alert">
          {errors.root.server.message}
        </Notice>
      )}

      <div className="sticky bottom-0 -mx-1 flex flex-col-reverse gap-2 border-t border-line bg-paper/95 px-1 py-3 sm:flex-row sm:items-center sm:justify-end">
        {isDirty && <span className="text-[13px] text-muted sm:mr-auto">You have unsaved changes.</span>}
        <Button variant="secondary" disabled={!isDirty || isSubmitting} onClick={() => reset(settingsToForm(settings))}>
          Discard
        </Button>
        <Button type="submit" loading={isSubmitting}>
          Save settings
        </Button>
      </div>
    </form>
  )
}
