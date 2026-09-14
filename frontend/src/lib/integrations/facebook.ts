import { useEffect, useState } from 'react'
import type { EmbeddedSignupRequest, SignupConfig } from '../../api/types'
import { loadScript } from './loadScript'

/** What Embedded Signup returns; post it to `POST /api/v1/whatsapp/embedded-signup/`. */
export type EmbeddedSignupResult = Required<Pick<EmbeddedSignupRequest, 'code' | 'waba_id'>> & {
  phone_number_id: string
  business_id: string
}

export class EmbeddedSignupCancelled extends Error {
  readonly step: string | null
  constructor(step: string | null = null) {
    super('WhatsApp signup was closed before it finished.')
    this.name = 'EmbeddedSignupCancelled'
    this.step = step
  }
}

export interface EmbeddedSignupLauncher {
  /** Opens Meta's Embedded Signup popup. Must be called from a click handler (popup blockers). */
  launch(config: SignupConfig): Promise<EmbeddedSignupResult>
}

type FacebookSdk = {
  init(options: { appId: string; autoLogAppEvents: boolean; xfbml: boolean; version: string }): void
  login(
    callback: (response: { authResponse?: { code?: string } | null; status?: string }) => void,
    options: Record<string, unknown>,
  ): void
}

declare global {
  interface Window {
    FB?: FacebookSdk
    fbAsyncInit?: () => void
  }
}

type SessionInfo = { type?: string; event?: string; data?: { phone_number_id?: string; waba_id?: string; business_id?: string; current_step?: string } }

let initialisedAppId: string | null = null

async function ensureSdk(config: SignupConfig): Promise<FacebookSdk> {
  await loadScript('https://connect.facebook.net/en_US/sdk.js', { crossorigin: 'anonymous' })
  const fb = window.FB
  if (!fb) throw new Error('Facebook SDK did not initialise')
  if (initialisedAppId !== config.app_id) {
    fb.init({ appId: config.app_id, autoLogAppEvents: true, xfbml: false, version: config.graph_api_version })
    initialisedAppId = config.app_id
  }
  return fb
}

const realLauncher: EmbeddedSignupLauncher = {
  async launch(config) {
    const fb = await ensureSdk(config)

    return new Promise<EmbeddedSignupResult>((resolve, reject) => {
      let session: SessionInfo['data'] | null = null
      let code: string | null = null
      let cancelledStep: string | null = null
      let settled = false

      const finish = () => {
        if (settled || !code || !session?.waba_id) return
        settled = true
        window.removeEventListener('message', onMessage)
        resolve({
          code,
          waba_id: session.waba_id,
          phone_number_id: session.phone_number_id ?? '',
          business_id: session.business_id ?? '',
        })
      }

      const onMessage = (event: MessageEvent) => {
        if (!/(^|\.)facebook\.com$/.test(new URL(event.origin).hostname)) return
        let payload: SessionInfo
        try {
          payload = typeof event.data === 'string' ? (JSON.parse(event.data) as SessionInfo) : (event.data as SessionInfo)
        } catch {
          return
        }
        if (payload.type !== 'WA_EMBEDDED_SIGNUP') return
        if (payload.event === 'CANCEL') cancelledStep = payload.data?.current_step ?? null
        if (payload.event === 'FINISH' || payload.event === 'FINISH_ONLY_WABA') {
          session = payload.data ?? null
          finish()
        }
      }
      window.addEventListener('message', onMessage)

      fb.login(
        (response) => {
          code = response.authResponse?.code ?? null
          if (!code) {
            settled = true
            window.removeEventListener('message', onMessage)
            reject(new EmbeddedSignupCancelled(cancelledStep))
            return
          }
          // The session-info message can arrive after the login callback.
          finish()
          setTimeout(() => {
            if (settled) return
            settled = true
            window.removeEventListener('message', onMessage)
            reject(new Error('Meta did not return the WhatsApp Business Account. Please try again.'))
          }, 10_000)
        },
        {
          config_id: config.config_id,
          response_type: 'code',
          override_default_response_type: true,
          extras: { setup: {}, sessionInfoVersion: '3' },
        },
      )
    })
  },
}

/** Mock launcher: resolves with fake ids after a short delay, no popup. */
export const mockEmbeddedSignupLauncher: EmbeddedSignupLauncher = {
  launch: () =>
    new Promise((resolve) =>
      setTimeout(
        () =>
          resolve({
            code: `mock-code-${Date.now()}`,
            waba_id: '109283746501928',
            phone_number_id: '110293847561029',
            business_id: '564738291056473',
          }),
        900,
      ),
    ),
}

/**
 * Embedded Signup behind an interface. In mock mode no Meta script is loaded.
 * `ready` turns true once the SDK has loaded (immediately in mock mode).
 */
export function useFacebookSdk(config: SignupConfig | undefined): { ready: boolean; error: Error | null; launcher: EmbeddedSignupLauncher } {
  const isMock = import.meta.env.VITE_API_MODE === 'mock'
  const [state, setState] = useState<{ ready: boolean; error: Error | null }>({ ready: isMock, error: null })

  useEffect(() => {
    if (isMock || !config) return
    let active = true
    ensureSdk(config).then(
      () => active && setState({ ready: true, error: null }),
      (error: unknown) => active && setState({ ready: false, error: error instanceof Error ? error : new Error(String(error)) }),
    )
    return () => {
      active = false
    }
  }, [isMock, config])

  return { ...state, launcher: isMock ? mockEmbeddedSignupLauncher : realLauncher }
}
