/**
 * A line-by-line port of `backend/apps/message_templates/validators.py`. Messages, limits and
 * rules match the backend exactly, so the builder rejects what the API would reject and the mock
 * API answers like the real one. Keep the two in sync.
 */

export const NAME_MAX_LENGTH = 512
export const NAME_RE = /^[a-z0-9_]+$/
/** ISO 639 language, optionally with a region: en, hi, fil, en_US, pt_BR. */
export const LANGUAGE_RE = /^[a-z]{2,3}(_[A-Z]{2})?$/

export const BODY_MAX_LENGTH = 1024
export const HEADER_TEXT_MAX_LENGTH = 60
export const FOOTER_MAX_LENGTH = 60
export const BUTTON_TEXT_MAX_LENGTH = 25
export const COPY_CODE_MAX_LENGTH = 15
export const MAX_BUTTONS = 10
export const MAX_URL_BUTTONS = 2
export const MAX_PHONE_BUTTONS = 1
export const MAX_COPY_CODE_BUTTONS = 1
export const CODE_EXPIRATION_RANGE = [1, 90] as const

export const CATEGORIES = ['MARKETING', 'UTILITY', 'AUTHENTICATION'] as const
export const COMPONENT_TYPES = ['HEADER', 'BODY', 'FOOTER', 'BUTTONS'] as const
export const TEXT_HEADER = 'TEXT'
export const MEDIA_HEADER_FORMATS = ['IMAGE', 'VIDEO', 'DOCUMENT', 'LOCATION'] as const
export const OTP_TYPES = ['COPY_CODE', 'ONE_TAP', 'ZERO_TAP'] as const

const PLACEHOLDER_RE = /\{\{(.*?)\}\}/g
const POSITIONAL_RE = /^[1-9][0-9]*$/
const NAMED_RE = /^[a-zA-Z_][a-zA-Z0-9_]*$/
const LEADING_PLACEHOLDER_RE = /^\{\{[^{}]*\}\}/
const TRAILING_PLACEHOLDER_RE = /\{\{[^{}]*\}\}$/
const PHONE_RE = /^\+?[0-9]{6,20}$/
const URL_RE = /^https?:\/\/\S+$/

type Json = Record<string, unknown>

export type TemplateErrors = Partial<Record<'name' | 'language' | 'category' | 'components', string[]>>

function isRecord(value: unknown): value is Json {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Length in code points, like Python's `len(str)`. */
export function textLength(text: string): number {
  return [...text].length
}

function isBlank(value: string): boolean {
  return value.trim() === ''
}

function placeholders(text: string): string[] {
  return [...text.matchAll(PLACEHOLDER_RE)].map((match) => match[1])
}

/** Positional variable numbers in `text` in order of appearance; ignores anything else. */
export function variableNumbers(text: unknown): number[] {
  if (typeof text !== 'string') return []
  return placeholders(text)
    .filter((inner) => POSITIONAL_RE.test(inner))
    .map(Number)
}

/** Number of distinct positional variables (`{{1}} .. {{n}}`) in `text`. */
export function variableCount(text: unknown): number {
  return new Set(variableNumbers(text)).size
}

export function hasPlaceholder(text: string): boolean {
  return placeholders(text).length > 0
}

export function nameErrors(name: unknown): string[] {
  if (typeof name !== 'string' || !name) return ['Name is required.']
  if (textLength(name) > NAME_MAX_LENGTH) return [`Name must be at most ${NAME_MAX_LENGTH} characters.`]
  if (!NAME_RE.test(name)) {
    return ['Name may contain only lowercase letters, digits and underscores (e.g. order_update).']
  }
  return []
}

export function languageErrors(language: unknown): string[] {
  if (typeof language !== 'string' || !LANGUAGE_RE.test(language)) {
    return ['Language must be a Meta language code such as en, hi or en_US.']
  }
  return []
}

export function categoryErrors(category: unknown): string[] {
  return (CATEGORIES as readonly unknown[]).includes(category) ? [] : [`Category must be one of ${CATEGORIES.join(', ')}.`]
}

/** Validates a whole template; returns errors keyed by field (empty object when valid). */
export function validateTemplate(input: { name: unknown; language: unknown; category: unknown; components: unknown }): TemplateErrors {
  const errors: TemplateErrors = {}
  const name = nameErrors(input.name)
  if (name.length) errors.name = name
  const language = languageErrors(input.language)
  if (language.length) errors.language = language
  const category = categoryErrors(input.category)
  if (category.length) errors.category = category
  else {
    const components = validateComponents(input.components, input.category as string)
    if (components.length) errors.components = components
  }
  return errors
}

/** Validates `components` (Meta's format) for `category`; returns a list of messages. */
export function validateComponents(components: unknown, category: string): string[] {
  const errors: string[] = []
  if (!Array.isArray(components) || components.length === 0) return ['Components must be a non-empty list.']

  const byType = new Map<string, Json>()
  components.forEach((component, index) => {
    if (!isRecord(component) || typeof component.type !== 'string') {
      errors.push(`Component ${index + 1} must be an object with a type.`)
      return
    }
    const type = component.type.toUpperCase()
    if (!(COMPONENT_TYPES as readonly string[]).includes(type)) {
      errors.push(`Component type '${component.type}' is not supported; use ${COMPONENT_TYPES.join(', ')}.`)
    } else if (byType.has(type)) {
      errors.push(`Only one ${type} component is allowed.`)
    } else {
      byType.set(type, component)
    }
  })

  if (!byType.has('BODY')) errors.push('Templates need exactly one BODY component.')

  if (category === 'AUTHENTICATION') {
    checkAuthentication(byType, errors)
  } else {
    const header = byType.get('HEADER')
    const body = byType.get('BODY')
    const footer = byType.get('FOOTER')
    const buttons = byType.get('BUTTONS')
    if (header) checkHeader(header, errors)
    if (body) checkBody(body, errors)
    if (footer) checkFooter(footer, errors)
    if (buttons) checkButtons(buttons, errors)
  }
  return errors
}

// --- Standard templates ---------------------------------------------------------------------

/** Positional numbers in `text`; records an error and returns null on bad placeholders. */
function parseVariables(text: string, where: string, errors: string[]): number[] | null {
  const numbers: number[] = []
  let valid = true
  for (const inner of placeholders(text)) {
    if (POSITIONAL_RE.test(inner)) {
      numbers.push(Number(inner))
    } else if (NAMED_RE.test(inner.trim())) {
      errors.push(
        `${where}: named variables like {{${inner.trim()}}} are not supported yet; use positional variables such as {{1}}.`,
      )
      valid = false
    } else {
      errors.push(`${where}: {{${inner}}} is not a valid variable; write variables as {{1}}, {{2}}, ... without spaces.`)
      valid = false
    }
  }
  if (!valid) return null
  const distinct = [...new Set(numbers)].sort((a, b) => a - b)
  if (distinct.some((n, i) => n !== i + 1)) {
    const found = distinct.map((n) => `{{${n}}}`).join(', ')
    errors.push(`${where}: variables must be numbered sequentially from {{1}} (${found}).`)
    return null
  }
  return numbers
}

function componentText(component: Json, where: string, maxLength: number, errors: string[]): string {
  const text = component.text
  if (typeof text !== 'string' || isBlank(text)) {
    errors.push(`${where}: text is required.`)
    return ''
  }
  const length = textLength(text)
  if (length > maxLength) errors.push(`${where}: text must be at most ${maxLength} characters (has ${length}).`)
  return text
}

function exampleValues(component: Json, key: string): unknown {
  return isRecord(component.example) ? component.example[key] : undefined
}

function truthy(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0
  if (isRecord(value)) return Object.keys(value).length > 0
  return Boolean(value)
}

/** `values` must be a list of `expected` non-empty strings (or absent when 0). */
function checkSamples(values: unknown, expected: number, where: string, errors: string[]) {
  if (expected === 0) {
    if (truthy(values)) errors.push(`${where}: example values are given but the text has no variables.`)
    return
  }
  if (!Array.isArray(values) || !values.every((v) => typeof v === 'string' && !isBlank(v))) {
    errors.push(`${where}: provide ${expected} example value(s), one non-empty string per variable.`)
    return
  }
  if (values.length !== expected) {
    errors.push(`${where}: ${expected} variable(s) need ${expected} example value(s) (found ${values.length}).`)
  }
}

function checkHeader(component: Json, errors: string[]) {
  const format = String(component.format ?? '').toUpperCase()
  if (format === TEXT_HEADER) {
    const text = componentText(component, 'HEADER', HEADER_TEXT_MAX_LENGTH, errors)
    const numbers = text ? parseVariables(text, 'HEADER', errors) : []
    if (numbers === null) return
    const count = new Set(numbers).size
    if (count > 1 || numbers.length > 1) {
      errors.push('HEADER: text headers may contain at most one variable, {{1}}.')
      return
    }
    checkSamples(exampleValues(component, 'header_text'), count, 'HEADER', errors)
  } else if ((MEDIA_HEADER_FORMATS as readonly string[]).includes(format)) {
    if (truthy(component.text)) errors.push(`HEADER: ${format} headers cannot have text.`)
  } else {
    errors.push(`HEADER: format must be one of ${[TEXT_HEADER, ...MEDIA_HEADER_FORMATS].join(', ')}.`)
  }
}

function checkBody(component: Json, errors: string[]) {
  const text = componentText(component, 'BODY', BODY_MAX_LENGTH, errors)
  if (!text) return
  const numbers = parseVariables(text, 'BODY', errors)
  if (numbers === null) return
  const stripped = text.trim()
  if (LEADING_PLACEHOLDER_RE.test(stripped) || TRAILING_PLACEHOLDER_RE.test(stripped)) {
    errors.push('BODY: text cannot start or end with a variable.')
  }
  const count = new Set(numbers).size
  let samples = exampleValues(component, 'body_text')
  if (Array.isArray(samples) && samples.length === 1 && Array.isArray(samples[0])) {
    samples = samples[0]
  } else if (truthy(samples) && count) {
    errors.push('BODY: example.body_text must be a list holding one list of sample values.')
    return
  }
  checkSamples(samples, count, 'BODY', errors)
}

function checkFooter(component: Json, errors: string[]) {
  const text = componentText(component, 'FOOTER', FOOTER_MAX_LENGTH, errors)
  if (hasPlaceholder(text)) errors.push('FOOTER: text cannot contain variables.')
}

function buttonText(button: Json, where: string, errors: string[]) {
  const text = button.text
  if (typeof text !== 'string' || isBlank(text)) errors.push(`${where}: text is required.`)
  else if (textLength(text) > BUTTON_TEXT_MAX_LENGTH) errors.push(`${where}: text must be at most ${BUTTON_TEXT_MAX_LENGTH} characters.`)
}

function checkButtons(component: Json, errors: string[]) {
  const buttons = component.buttons
  if (!Array.isArray(buttons) || buttons.length === 0) {
    errors.push('BUTTONS: add at least one button.')
    return
  }
  if (buttons.length > MAX_BUTTONS) errors.push(`BUTTONS: at most ${MAX_BUTTONS} buttons are allowed.`)

  const counts: Record<'URL' | 'PHONE_NUMBER' | 'COPY_CODE', number> = { URL: 0, PHONE_NUMBER: 0, COPY_CODE: 0 }
  const kinds: boolean[] = []
  buttons.forEach((button, index) => {
    const where = `BUTTONS[${index}]`
    if (!isRecord(button) || typeof button.type !== 'string') {
      errors.push(`${where}: must be an object with a type.`)
      return
    }
    const type = button.type.toUpperCase()
    kinds.push(type === 'QUICK_REPLY')
    if (type in counts) counts[type as keyof typeof counts] += 1
    if (type === 'QUICK_REPLY') {
      buttonText(button, where, errors)
    } else if (type === 'URL') {
      buttonText(button, where, errors)
      checkUrlButton(button, where, errors)
    } else if (type === 'PHONE_NUMBER') {
      buttonText(button, where, errors)
      const phone = button.phone_number
      if (typeof phone !== 'string' || !PHONE_RE.test(phone)) {
        errors.push(`${where}: phone_number must be a number such as +919800041207.`)
      }
    } else if (type === 'COPY_CODE') {
      const example = button.example
      if (typeof example !== 'string' || isBlank(example)) {
        errors.push(`${where}: example (a sample offer code) is required.`)
      } else if (textLength(example) > COPY_CODE_MAX_LENGTH) {
        errors.push(`${where}: offer code example must be at most ${COPY_CODE_MAX_LENGTH} characters.`)
      }
    } else if (type === 'OTP') {
      errors.push(`${where}: OTP buttons are only allowed in AUTHENTICATION templates.`)
    } else {
      errors.push(`${where}: button type '${button.type}' is not supported yet.`)
    }
  })

  const limits = { URL: MAX_URL_BUTTONS, PHONE_NUMBER: MAX_PHONE_BUTTONS, COPY_CODE: MAX_COPY_CODE_BUTTONS }
  for (const [type, limit] of Object.entries(limits)) {
    if (counts[type as keyof typeof counts] > limit) errors.push(`BUTTONS: at most ${limit} ${type} button(s) are allowed.`)
  }
  const groupChanges = kinds.slice(1).filter((kind, i) => kind !== kinds[i]).length
  if (groupChanges > 1) errors.push('BUTTONS: keep QUICK_REPLY buttons together, before or after the others.')
}

function checkUrlButton(button: Json, where: string, errors: string[]) {
  const url = button.url
  if (typeof url !== 'string' || !URL_RE.test(url)) {
    errors.push(`${where}: url must start with http:// or https://.`)
    return
  }
  const numbers = parseVariables(url, where, errors)
  if (numbers === null) return
  if (numbers.length > 1) {
    errors.push(`${where}: a URL may contain at most one variable, {{1}}.`)
    return
  }
  if (numbers.length && !url.endsWith('{{1}}')) {
    errors.push(`${where}: the URL variable must be at the end, e.g. https://x.in/{{1}}.`)
    return
  }
  const example = typeof button.example === 'string' ? [button.example] : button.example
  checkSamples(example, numbers.length, where, errors)
}

// --- Authentication templates ---------------------------------------------------------------

function checkAuthentication(byType: Map<string, Json>, errors: string[]) {
  if (byType.has('HEADER')) errors.push('AUTHENTICATION templates cannot have a HEADER.')

  const body = byType.get('BODY')
  if (body) {
    const flag = body.add_security_recommendation
    if (flag !== undefined && flag !== null && typeof flag !== 'boolean') {
      errors.push('BODY: add_security_recommendation must be true or false.')
    }
  }

  const footer = byType.get('FOOTER')
  if (footer) {
    const minutes = footer.code_expiration_minutes
    const [low, high] = CODE_EXPIRATION_RANGE
    if (minutes !== undefined && minutes !== null && (typeof minutes !== 'number' || !Number.isInteger(minutes) || minutes < low || minutes > high)) {
      errors.push(`FOOTER: code_expiration_minutes must be a whole number ${low}-${high}.`)
    }
  }

  const buttons = byType.get('BUTTONS')?.buttons
  if (!Array.isArray(buttons) || buttons.length !== 1) {
    errors.push('AUTHENTICATION templates need exactly one OTP button.')
    return
  }
  const button: unknown = buttons[0]
  if (!isRecord(button) || String(button.type ?? '').toUpperCase() !== 'OTP') {
    errors.push('BUTTONS[0]: AUTHENTICATION templates only allow an OTP button.')
    return
  }
  const otpType = String(button.otp_type ?? '').toUpperCase()
  if (!(OTP_TYPES as readonly string[]).includes(otpType)) {
    errors.push(`BUTTONS[0]: otp_type must be one of ${OTP_TYPES.join(', ')}.`)
  } else if (otpType !== 'COPY_CODE' && !(truthy(button.supported_apps) || (truthy(button.package_name) && truthy(button.signature_hash)))) {
    errors.push(`BUTTONS[0]: ${otpType} buttons need supported_apps (package_name and signature_hash).`)
  }
  const text = button.text
  if (text !== undefined && text !== null && (typeof text !== 'string' || textLength(text) > BUTTON_TEXT_MAX_LENGTH)) {
    errors.push(`BUTTONS[0]: text must be at most ${BUTTON_TEXT_MAX_LENGTH} characters.`)
  }
}
