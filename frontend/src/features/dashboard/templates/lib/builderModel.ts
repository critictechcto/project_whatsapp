import type { MessageTemplate, Schemas, TemplateCategory } from '../../../../api/types'
import type { PreviewMessage } from '../../../../components/app/whatsapp/template'
import { variableNumbers } from './validate'

export type HeaderType = 'NONE' | 'TEXT' | 'IMAGE' | 'VIDEO' | 'DOCUMENT' | 'LOCATION'
export type ButtonType = 'QUICK_REPLY' | 'URL' | 'PHONE_NUMBER' | 'COPY_CODE'
export type OtpType = 'COPY_CODE' | 'ONE_TAP'

/** One button row. Flat so react-hook-form's field array stays simple; unused fields stay ''. */
export type ButtonValues = {
  type: ButtonType
  text: string
  url: string
  /** Sample value for the URL's `{{1}}`. */
  urlExample: string
  phoneNumber: string
  /** Sample offer code for COPY_CODE. */
  code: string
}

export type BuilderValues = {
  waba: string
  name: string
  category: TemplateCategory
  language: string
  headerType: HeaderType
  headerText: string
  headerExample: string
  /** Meta media handle for the header sample (`example.header_handle`). */
  headerHandle: string
  bodyText: string
  /** Example for `{{n}}` at index n-1. */
  bodyExamples: string[]
  footerText: string
  buttons: ButtonValues[]
  // AUTHENTICATION
  addSecurityRecommendation: boolean
  /** '' for no expiry note. */
  codeExpirationMinutes: string
  otpType: OtpType
  otpButtonText: string
  packageName: string
  signatureHash: string
}

export const defaultBuilderValues: BuilderValues = {
  waba: '',
  name: '',
  category: 'UTILITY',
  language: 'en',
  headerType: 'NONE',
  headerText: '',
  headerExample: '',
  headerHandle: '',
  bodyText: '',
  bodyExamples: [],
  footerText: '',
  buttons: [],
  addSecurityRecommendation: true,
  codeExpirationMinutes: '10',
  otpType: 'COPY_CODE',
  otpButtonText: '',
  packageName: '',
  signatureHash: '',
}

export function emptyButton(type: ButtonType): ButtonValues {
  return { type, text: '', url: '', urlExample: '', phoneNumber: '', code: '' }
}

/** "Order Update-2" → "order_update_2": lowercase, spaces and dashes become underscores, other characters drop. */
export function formatTemplateName(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
}

/** Distinct positional variables, sorted: "Hi {{2}} {{1}} {{2}}" → [1, 2]. */
export function distinctVariables(text: string): number[] {
  return [...new Set(variableNumbers(text))].sort((a, b) => a - b)
}

/** The next variable to insert: one past the highest in use. */
export function nextVariable(text: string): number {
  return Math.max(0, ...variableNumbers(text)) + 1
}

/** Replaces `{{n}}` with `values[n-1]` when present; other placeholders stay visible. */
export function fillPositional(text: string, values: readonly string[]): string {
  return text.replace(/\{\{([1-9][0-9]*)\}\}/g, (placeholder, n: string) => {
    const value = values[Number(n) - 1]
    return value?.trim() ? value : placeholder
  })
}

type Component = Record<string, unknown>

function urlHasVariable(url: string) {
  return variableNumbers(url).length > 0
}

/** Form values → the API payload (Meta's component format). */
export function toTemplateRequest(values: BuilderValues): Schemas['MessageTemplateRequest'] {
  return {
    waba: values.waba,
    name: values.name,
    language: values.language,
    category: values.category,
    components: values.category === 'AUTHENTICATION' ? authenticationComponents(values) : standardComponents(values),
  }
}

function standardComponents(values: BuilderValues): Component[] {
  const components: Component[] = []

  if (values.headerType === 'TEXT') {
    const header: Component = { type: 'HEADER', format: 'TEXT', text: values.headerText }
    if (variableNumbers(values.headerText).length) header.example = { header_text: [values.headerExample] }
    components.push(header)
  } else if (values.headerType !== 'NONE') {
    const header: Component = { type: 'HEADER', format: values.headerType }
    if (values.headerHandle.trim()) header.example = { header_handle: [values.headerHandle.trim()] }
    components.push(header)
  }

  const body: Component = { type: 'BODY', text: values.bodyText }
  const count = distinctVariables(values.bodyText).length
  if (count) body.example = { body_text: [Array.from({ length: count }, (_, i) => values.bodyExamples[i] ?? '')] }
  components.push(body)

  if (values.footerText.trim()) components.push({ type: 'FOOTER', text: values.footerText })

  if (values.buttons.length) {
    components.push({
      type: 'BUTTONS',
      buttons: values.buttons.map((button): Component => {
        switch (button.type) {
          case 'QUICK_REPLY':
            return { type: 'QUICK_REPLY', text: button.text }
          case 'URL': {
            const url: Component = { type: 'URL', text: button.text, url: button.url }
            // Meta's example for a variable URL is the full sample URL.
            if (urlHasVariable(button.url) && button.urlExample.trim()) url.example = [button.url.replace('{{1}}', button.urlExample.trim())]
            return url
          }
          case 'PHONE_NUMBER':
            return { type: 'PHONE_NUMBER', text: button.text, phone_number: button.phoneNumber }
          case 'COPY_CODE':
            return { type: 'COPY_CODE', example: button.code }
        }
      }),
    })
  }
  return components
}

function authenticationComponents(values: BuilderValues): Component[] {
  const components: Component[] = [{ type: 'BODY', add_security_recommendation: values.addSecurityRecommendation }]
  const minutes = values.codeExpirationMinutes.trim()
  if (minutes) components.push({ type: 'FOOTER', code_expiration_minutes: /^\d+$/.test(minutes) ? Number(minutes) : minutes })
  const otp: Component = { type: 'OTP', otp_type: values.otpType }
  if (values.otpButtonText.trim()) otp.text = values.otpButtonText
  if (values.otpType === 'ONE_TAP' && values.packageName.trim() && values.signatureHash.trim()) {
    otp.supported_apps = [{ package_name: values.packageName.trim(), signature_hash: values.signatureHash.trim() }]
  }
  components.push({ type: 'BUTTONS', buttons: [otp] })
  return components
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

/** An existing template → form values, for editing or duplicating. */
export function fromTemplate(template: Pick<MessageTemplate, 'waba' | 'name' | 'language' | 'category' | 'components'>): BuilderValues {
  const values: BuilderValues = {
    ...defaultBuilderValues,
    waba: template.waba,
    name: template.name,
    language: template.language,
    category: template.category,
    buttons: [],
  }
  const byType = new Map<string, Record<string, unknown>>()
  for (const component of template.components) {
    const record = asRecord(component)
    if (typeof record.type === 'string' && !byType.has(record.type.toUpperCase())) byType.set(record.type.toUpperCase(), record)
  }

  const header = byType.get('HEADER')
  const body = byType.get('BODY')
  const footer = byType.get('FOOTER')
  const buttons = Array.isArray(byType.get('BUTTONS')?.buttons) ? (byType.get('BUTTONS')?.buttons as unknown[]).map(asRecord) : []

  if (template.category === 'AUTHENTICATION') {
    values.addSecurityRecommendation = body?.add_security_recommendation === true
    const minutes = footer?.code_expiration_minutes
    values.codeExpirationMinutes = typeof minutes === 'number' ? String(minutes) : ''
    const otp = buttons[0]
    if (otp) {
      values.otpType = str(otp.otp_type).toUpperCase() === 'ONE_TAP' ? 'ONE_TAP' : 'COPY_CODE'
      values.otpButtonText = str(otp.text)
      const app = asRecord(Array.isArray(otp.supported_apps) ? otp.supported_apps[0] : undefined)
      values.packageName = str(app.package_name ?? otp.package_name)
      values.signatureHash = str(app.signature_hash ?? otp.signature_hash)
    }
    return values
  }

  if (header) {
    const format = str(header.format).toUpperCase()
    const example = asRecord(header.example)
    if (format === 'TEXT') {
      values.headerType = 'TEXT'
      values.headerText = str(header.text)
      values.headerExample = Array.isArray(example.header_text) ? str(example.header_text[0]) : ''
    } else if (['IMAGE', 'VIDEO', 'DOCUMENT', 'LOCATION'].includes(format)) {
      values.headerType = format as HeaderType
      values.headerHandle = Array.isArray(example.header_handle) ? str(example.header_handle[0]) : ''
    }
  }
  if (body) {
    values.bodyText = str(body.text)
    const samples = asRecord(body.example).body_text
    const first = Array.isArray(samples) && Array.isArray(samples[0]) ? (samples[0] as unknown[]) : []
    values.bodyExamples = first.map(str)
  }
  values.footerText = str(footer?.text)
  values.buttons = buttons.flatMap((button): ButtonValues[] => {
    const type = str(button.type).toUpperCase()
    if (type === 'QUICK_REPLY') return [{ ...emptyButton('QUICK_REPLY'), text: str(button.text) }]
    if (type === 'PHONE_NUMBER') return [{ ...emptyButton('PHONE_NUMBER'), text: str(button.text), phoneNumber: str(button.phone_number) }]
    if (type === 'COPY_CODE') return [{ ...emptyButton('COPY_CODE'), code: str(button.example) }]
    if (type === 'URL') {
      const url = str(button.url)
      const sample = Array.isArray(button.example) ? str(button.example[0]) : str(button.example)
      const prefix = url.split('{{1}}')[0]
      const urlExample = url.includes('{{1}}') && sample.startsWith(prefix) ? sample.slice(prefix.length) : sample
      return [{ ...emptyButton('URL'), text: str(button.text), url, urlExample }]
    }
    return []
  })
  return values
}

export const AUTH_SAMPLE_CODE = '482913'

/** What the customer will see, with example values filled in. */
export function previewFromValues(values: BuilderValues): PreviewMessage {
  if (values.category === 'AUTHENTICATION') {
    const minutes = values.codeExpirationMinutes.trim()
    return {
      body: `*${AUTH_SAMPLE_CODE}* is your verification code.${values.addSecurityRecommendation ? ' For your security, do not share this code.' : ''}`,
      footer: minutes ? `This code expires in ${minutes} minutes.` : null,
      buttons: [{ type: 'OTP', text: values.otpButtonText.trim() || (values.otpType === 'ONE_TAP' ? 'Autofill' : 'Copy code') }],
    }
  }

  const header: PreviewMessage['header'] =
    values.headerType === 'NONE'
      ? undefined
      : values.headerType === 'TEXT'
        ? { format: 'TEXT', text: fillPositional(values.headerText, [values.headerExample]) }
        : { format: values.headerType }

  return {
    header,
    body: fillPositional(values.bodyText, values.bodyExamples),
    footer: values.footerText.trim() ? values.footerText : null,
    buttons: values.buttons.map((button) => ({
      type: button.type,
      text: button.type === 'COPY_CODE' ? 'Copy offer code' : button.text || buttonTypeLabels[button.type],
    })),
  }
}

export const buttonTypeLabels: Record<ButtonType, string> = {
  QUICK_REPLY: 'Quick reply',
  URL: 'Visit website',
  PHONE_NUMBER: 'Call phone number',
  COPY_CODE: 'Copy offer code',
}

/** A stored template's preview with its own example values, for list and detail views. */
export function previewFromTemplate(template: Pick<MessageTemplate, 'waba' | 'name' | 'language' | 'category' | 'components'>): PreviewMessage {
  return previewFromValues(fromTemplate(template))
}
