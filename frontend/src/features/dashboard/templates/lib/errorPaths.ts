import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import { applyApiErrorToForm, flattenDetails, isApiError } from '../../../../api/errors'
import type { BuilderValues } from './builderModel'

/** Where an error shows in the builder. `root.template` renders in the error summary only. */
export type BuilderIssue = { path: string; message: string }

const PREFIX_RE = /^(HEADER|BODY|FOOTER|BUTTONS)(?:\[(\d+)\])?:\s*(.*)$/s

function sentence(message: string): string {
  return message.charAt(0).toUpperCase() + message.slice(1)
}

/**
 * Maps one message from the API's `components` list (e.g. `"BUTTONS[1]: text is required."`)
 * onto a builder field, dropping the component prefix.
 */
export function issueForComponentMessage(raw: string, values: BuilderValues): BuilderIssue {
  const auth = values.category === 'AUTHENTICATION'
  if (raw === 'Templates need exactly one BODY component.') return { path: auth ? 'addSecurityRecommendation' : 'bodyText', message: raw }
  if (raw === 'AUTHENTICATION templates need exactly one OTP button.') return { path: 'otpType', message: raw }

  const match = PREFIX_RE.exec(raw)
  if (!match) return { path: 'root.template', message: raw }
  const [, component, indexText, rest] = match
  const message = sentence(rest)
  const lower = rest.toLowerCase()

  if (component === 'HEADER') {
    if (lower.includes('example')) return { path: 'headerExample', message }
    return { path: values.headerType === 'TEXT' ? 'headerText' : 'headerType', message }
  }
  if (component === 'BODY') {
    if (auth) return { path: 'addSecurityRecommendation', message }
    return { path: lower.includes('example') ? 'bodyExamples' : 'bodyText', message }
  }
  if (component === 'FOOTER') return { path: auth ? 'codeExpirationMinutes' : 'footerText', message }

  // BUTTONS
  if (indexText === undefined) return { path: auth ? 'otpType' : 'buttons', message }
  const index = Number(indexText)
  if (auth) {
    if (lower.includes('supported_apps')) return { path: 'packageName', message }
    if (lower.includes('text')) return { path: 'otpButtonText', message }
    return { path: 'otpType', message }
  }
  const button = values.buttons[index]
  const at = (field: string) => ({ path: `buttons.${index}.${field}`, message })
  if (!button) return { path: 'buttons', message }
  if (lower.includes('example')) return at(button.type === 'COPY_CODE' ? 'code' : 'urlExample')
  if (lower.includes('phone_number')) return at('phoneNumber')
  if (lower.startsWith('text')) return at('text')
  if (button.type === 'URL') return at('url')
  if (button.type === 'COPY_CODE') return at('code')
  return at('text')
}

const buttonFieldMap: Record<string, string> = { text: 'text', url: 'url', phone_number: 'phoneNumber' }

/** Maps a nested detail path like `components.2.buttons.1.url` onto a builder field. */
function issueForNestedPath(apiPath: string, message: string, values: BuilderValues, payload: { components: unknown[] }): BuilderIssue {
  const parts = apiPath.split('.')
  const component = payload.components[Number(parts[1])] as Record<string, unknown> | undefined
  const type = typeof component?.type === 'string' ? component.type.toUpperCase() : ''
  const auth = values.category === 'AUTHENTICATION'
  const field = parts[2] ?? ''

  if (type === 'HEADER') return { path: field === 'example' ? 'headerExample' : 'headerText', message }
  if (type === 'BODY') return { path: auth ? 'addSecurityRecommendation' : field === 'example' ? 'bodyExamples' : 'bodyText', message }
  if (type === 'FOOTER') return { path: auth ? 'codeExpirationMinutes' : 'footerText', message }
  if (type === 'BUTTONS' && field === 'buttons' && parts[3] !== undefined) {
    if (auth) return { path: parts[4] === 'text' ? 'otpButtonText' : 'otpType', message }
    const index = Number(parts[3])
    const button = values.buttons[index]
    const sub = parts[4] ?? 'text'
    if (sub === 'example') return { path: `buttons.${index}.${button?.type === 'COPY_CODE' ? 'code' : 'urlExample'}`, message }
    return { path: `buttons.${index}.${buttonFieldMap[sub] ?? 'text'}`, message }
  }
  if (type === 'BUTTONS') return { path: auth ? 'otpType' : 'buttons', message }
  return { path: 'root.template', message }
}

const TOP_LEVEL_FIELDS = new Set(['name', 'language', 'category', 'waba'])

/**
 * Applies an API error to the builder form. Handles the `components` message list the API returns
 * (`{"components": ["BODY: ...", "BUTTONS[0]: ..."]}`) and nested component details, and falls back
 * to `applyApiErrorToForm` for everything else. Returns true when a field error was applied.
 */
export function applyTemplateApiError<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  values: BuilderValues,
  payload: { components: unknown[] },
): boolean {
  if (!isApiError(error, 'invalid') || typeof error.details !== 'object' || error.details === null) {
    return applyApiErrorToForm(error, setError, { fields: [] })
  }

  const details = error.details as Record<string, unknown>
  const issues: BuilderIssue[] = []
  const rootMessages: string[] = []

  for (const [key, value] of Object.entries(details)) {
    if (key === 'components' && Array.isArray(value) && value.every((item) => typeof item === 'string')) {
      issues.push(...(value as string[]).map((message) => issueForComponentMessage(message, values)))
    } else if (key === 'components') {
      for (const [apiPath, message] of Object.entries(flattenDetails({ components: value }))) {
        issues.push(apiPath === 'components' ? { path: 'root.template', message } : issueForNestedPath(apiPath, message, values, payload))
      }
    } else if (TOP_LEVEL_FIELDS.has(key)) {
      const message = flattenDetails(value)['']
      if (message) issues.push({ path: key, message })
    } else {
      // `meta` (Meta rejected the request), non_field_errors and unknown keys.
      rootMessages.push(...Object.values(flattenDetails(value)))
    }
  }

  const seen = new Set<string>()
  let applied = false
  for (const issue of issues) {
    if (issue.path === 'root.template') {
      rootMessages.push(issue.message)
      continue
    }
    if (seen.has(issue.path)) continue
    seen.add(issue.path)
    setError(issue.path as Path<T>, { type: 'server', message: issue.message }, { shouldFocus: !applied })
    applied = true
  }
  if (rootMessages.length) setError('root.server' as Path<T>, { type: 'server', message: rootMessages.join(' ') })
  else if (!applied) setError('root.server' as Path<T>, { type: 'server', message: error.message })
  return applied
}
