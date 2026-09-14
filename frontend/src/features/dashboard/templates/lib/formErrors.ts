import { get, type FieldErrors } from 'react-hook-form'
import type { BuilderValues } from './builderModel'

export type FormIssue = { path: string; message: string }

const LEAF_KEYS = new Set(['message', 'type', 'ref', 'types'])

/** Every error message in react-hook-form's nested `errors`, with dotted paths. Array `root` errors use the array's path. */
export function collectErrors(errors: unknown, prefix = ''): FormIssue[] {
  if (typeof errors !== 'object' || errors === null) return []
  const record = errors as Record<string, unknown>
  const out: FormIssue[] = []
  if (prefix && typeof record.message === 'string' && record.message) out.push({ path: prefix, message: record.message })
  for (const [key, value] of Object.entries(record)) {
    if (LEAF_KEYS.has(key)) continue
    const path = !prefix ? key : key === 'root' ? prefix : `${prefix}.${key}`
    out.push(...collectErrors(value, path))
  }
  return out
}

/** The message at `path`, including a field array's `root` error. */
export function errorAt(errors: FieldErrors<BuilderValues>, path: string): string | undefined {
  const entry: unknown = get(errors, path)
  if (typeof entry !== 'object' || entry === null) return undefined
  const record = entry as { message?: unknown; root?: { message?: unknown } }
  if (typeof record.message === 'string' && record.message) return record.message
  if (typeof record.root?.message === 'string' && record.root.message) return record.root.message
  return undefined
}

const labels: Record<string, string> = {
  waba: 'WhatsApp account',
  name: 'Name',
  category: 'Category',
  language: 'Language',
  headerType: 'Header',
  headerText: 'Header text',
  headerExample: 'Header example',
  headerHandle: 'Header sample',
  bodyText: 'Message text',
  bodyExamples: 'Example values',
  footerText: 'Footer',
  buttons: 'Buttons',
  addSecurityRecommendation: 'Security note',
  codeExpirationMinutes: 'Code expiry',
  otpType: 'Code button',
  otpButtonText: 'Button text',
  packageName: 'Package name',
  signatureHash: 'Signature hash',
  'root.template': 'Template',
}

const buttonFieldLabels: Record<string, string> = {
  text: 'text',
  url: 'URL',
  urlExample: 'URL example',
  phoneNumber: 'phone number',
  code: 'offer code',
}

export function fieldLabel(path: string): string {
  const example = /^bodyExamples\.(\d+)$/.exec(path)
  if (example) return `Example for {{${Number(example[1]) + 1}}}`
  const button = /^buttons\.(\d+)\.(\w+)$/.exec(path)
  if (button) return `Button ${Number(button[1]) + 1} ${buttonFieldLabels[button[2]] ?? button[2]}`
  return labels[path] ?? path
}

const ORDER = Object.keys(labels)

/** Issues in page order, excluding the form-level server message (shown separately). */
export function orderedIssues(errors: FieldErrors<BuilderValues>): FormIssue[] {
  const rank = (path: string) => {
    const index = ORDER.indexOf(path.split('.')[0] === 'root' ? path : path.split('.')[0])
    return index === -1 ? ORDER.length : index
  }
  return collectErrors(errors)
    .filter((issue) => issue.path !== 'root.server')
    .sort((a, b) => rank(a.path) - rank(b.path) || a.path.localeCompare(b.path, undefined, { numeric: true }))
}
