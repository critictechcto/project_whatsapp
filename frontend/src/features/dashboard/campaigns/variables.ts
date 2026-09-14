import type { MessageTemplate, Schemas } from '../../../api/types'
import { templateVariables, type TemplateVariableValues } from '../../../components/app/whatsapp/template'
import type { VariableSource, VariableSourceType } from './api'

export const sourceTypeOptions: { value: VariableSourceType; label: string }[] = [
  { value: 'contact_field', label: 'Contact field' },
  { value: 'attribute', label: 'Contact attribute' },
  { value: 'static', label: 'Fixed text' },
]

export const contactFieldOptions = [
  { value: 'name', label: 'Name' },
  { value: 'phone_e164', label: 'Phone number' },
  { value: 'email', label: 'Email' },
] as const

export const contactFieldValues: readonly string[] = contactFieldOptions.map((option) => option.value)

/** Mapping as the wizard form holds it: buttons as a list so every entry has a stable form path. */
export type MappingForm = {
  header: VariableSource | null
  body: VariableSource[]
  buttons: { index: string; source: VariableSource }[]
}

export type SampleContact = {
  name?: string
  phone_e164: string
  email?: string
  attributes?: Record<string, unknown>
}

const staticSource = (): VariableSource => ({ source: 'static', value: '', fallback: '' })

/** The first body variable is usually a greeting, so it defaults to the contact's name. */
export function defaultBodySource(position: number): VariableSource {
  return position === 0 ? { source: 'contact_field', value: 'name', fallback: 'there' } : staticSource()
}

/** Shapes a mapping to the template's placeholders, keeping entries that already exist. */
export function normaliseMapping(template: Pick<MessageTemplate, 'components'>, current?: MappingForm): MappingForm {
  const spec = templateVariables(template)
  return {
    header: spec.header.names.length ? (current?.header ?? staticSource()) : null,
    body: spec.body.names.map((_, i) => current?.body[i] ?? defaultBodySource(i)),
    buttons: spec.buttons.map((button) => {
      const index = String(button.index)
      return current?.buttons.find((entry) => entry.index === index) ?? { index, source: staticSource() }
    }),
  }
}

export function mappingFromApi(mapping: Schemas['VariableMapping'] | undefined): MappingForm {
  return {
    header: mapping?.header ? { ...mapping.header } : null,
    body: (mapping?.body ?? []).map((source) => ({ ...source })),
    buttons: Object.entries(mapping?.buttons ?? {}).map(([index, source]) => ({ index, source: { ...source } })),
  }
}

export function mappingToApi(mapping: MappingForm): Schemas['VariableMappingRequest'] {
  return {
    header: mapping.header,
    body: mapping.body,
    buttons: Object.fromEntries(mapping.buttons.map((entry) => [entry.index, entry.source])),
  }
}

/** The value a source produces for a contact, falling back when it's blank. */
export function resolveSource(source: VariableSource, contact: SampleContact | null): string {
  let value = ''
  if (source.source === 'static') {
    value = source.value
  } else if (contact) {
    if (source.source === 'contact_field') {
      const fields: Record<string, string | undefined> = { name: contact.name, phone_e164: contact.phone_e164, email: contact.email }
      value = fields[source.value] ?? ''
    } else {
      const raw = contact.attributes?.[source.value.trim()]
      value = raw === undefined || raw === null ? '' : String(raw)
    }
  }
  return value.trim() ? value : source.fallback
}

export function previewValues(mapping: MappingForm, contact: SampleContact | null): TemplateVariableValues {
  return {
    header: mapping.header ? [resolveSource(mapping.header, contact)] : [],
    body: mapping.body.map((source) => resolveSource(source, contact)),
    buttons: Object.fromEntries(mapping.buttons.map((entry) => [entry.index, resolveSource(entry.source, contact)])),
  }
}

/** "Contact name (fallback “there”)" for summaries. */
export function describeSource(source: VariableSource): string {
  if (source.source === 'static') return source.value ? `“${source.value}”` : 'Fixed text (empty)'
  const what =
    source.source === 'contact_field'
      ? `Contact ${contactFieldOptions.find((option) => option.value === source.value)?.label.toLowerCase() ?? source.value}`
      : `Attribute “${source.value}”`
  return source.fallback ? `${what} (fallback “${source.fallback}”)` : what
}
