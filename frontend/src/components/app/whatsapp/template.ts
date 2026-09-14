import type { MessageTemplate } from '../../../api/types'

/** A template component in Meta's format (`HEADER`, `BODY`, `FOOTER`, `BUTTONS`). */
export type TemplateComponent = {
  type: string
  format?: string
  text?: string
  buttons?: TemplateButton[]
  example?: { body_text?: string[][]; header_text?: string[]; header_handle?: string[] }
}

export type TemplateButton = { type: string; text: string; url?: string; phone_number?: string; example?: string[] }

/** Values for a template's variables, in the order the placeholders first appear. */
export type TemplateVariableValues = {
  header: string[]
  body: string[]
  /** Button index (as string) → value for its single URL variable. */
  buttons: Record<string, string>
}

export const emptyVariableValues: TemplateVariableValues = { header: [], body: [], buttons: {} }

const PLACEHOLDER = /\{\{\s*([\w.]+)\s*\}\}/g

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function templateComponents(template: Pick<MessageTemplate, 'components'>): TemplateComponent[] {
  return template.components.filter(
    (component): component is TemplateComponent => isRecord(component) && typeof component.type === 'string',
  )
}

export function findComponent(template: Pick<MessageTemplate, 'components'>, type: string): TemplateComponent | undefined {
  return templateComponents(template).find((component) => component.type.toUpperCase() === type)
}

/** Unique placeholder names in order of appearance: `"Hi {{1}}, {{2}} {{1}}"` → `["1", "2"]`. */
export function extractVariables(text: string | undefined): string[] {
  if (!text) return []
  const names: string[] = []
  for (const match of text.matchAll(PLACEHOLDER)) {
    if (!names.includes(match[1])) names.push(match[1])
  }
  return names
}

/** Replaces placeholders by position among `extractVariables(text)`. Empty values keep the placeholder. */
export function fillVariables(text: string, values: readonly string[]): string {
  const names = extractVariables(text)
  return text.replace(PLACEHOLDER, (placeholder, name: string) => {
    const value = values[names.indexOf(name)]
    return value ? value : placeholder
  })
}

export type TemplateVariableSpec = {
  header: { names: string[]; examples: string[] }
  body: { names: string[]; examples: string[] }
  buttons: { index: number; text: string; names: string[]; example?: string }[]
}

/** Which variables a template needs, with Meta's sample values when present. */
export function templateVariables(template: Pick<MessageTemplate, 'components'>): TemplateVariableSpec {
  const header = findComponent(template, 'HEADER')
  const body = findComponent(template, 'BODY')
  const buttons = findComponent(template, 'BUTTONS')?.buttons ?? []

  return {
    header: {
      names: header?.format === 'TEXT' || !header?.format ? extractVariables(header?.text) : [],
      examples: header?.example?.header_text ?? [],
    },
    body: { names: extractVariables(body?.text), examples: body?.example?.body_text?.[0] ?? [] },
    buttons: buttons
      .map((button, index) => ({ index, text: button.text, names: extractVariables(button.url), example: button.example?.[0] }))
      .filter((button) => button.names.length > 0),
  }
}

export function countVariables(spec: TemplateVariableSpec): number {
  return spec.header.names.length + spec.body.names.length + spec.buttons.length
}

/** True when every variable has a non-blank value. */
export function variablesComplete(template: Pick<MessageTemplate, 'components'>, values: TemplateVariableValues): boolean {
  const spec = templateVariables(template)
  return (
    spec.header.names.every((_, i) => values.header[i]?.trim()) &&
    spec.body.names.every((_, i) => values.body[i]?.trim()) &&
    spec.buttons.every((button) => values.buttons[String(button.index)]?.trim())
  )
}

/**
 * Maps values onto `SendMessageRequest` fields (`body_params`, `header_param`, `button_params`).
 */
export function toSendParams(values: TemplateVariableValues): {
  body_params: string[]
  header_param?: string
  button_params?: Record<string, string>
} {
  return {
    body_params: values.body,
    ...(values.header[0] ? { header_param: values.header[0] } : {}),
    ...(Object.keys(values.buttons).length ? { button_params: values.buttons } : {}),
  }
}

export type PreviewMessage = {
  header?: { format: string; text?: string | null }
  body: string
  footer?: string | null
  buttons?: { type: string; text: string }[]
}

/** Builds preview content from a template and (partial) values. */
export function templatePreview(template: Pick<MessageTemplate, 'components'>, values: TemplateVariableValues = emptyVariableValues): PreviewMessage {
  const header = findComponent(template, 'HEADER')
  const body = findComponent(template, 'BODY')
  const footer = findComponent(template, 'FOOTER')
  const buttons = findComponent(template, 'BUTTONS')?.buttons ?? []

  return {
    header: header ? { format: header.format ?? 'TEXT', text: header.text ? fillVariables(header.text, values.header) : null } : undefined,
    body: body?.text ? fillVariables(body.text, values.body) : '',
    footer: footer?.text ?? null,
    buttons: buttons.map((button) => ({ type: button.type, text: button.text })),
  }
}

/** Sample values from the template's examples, for previews before the user types. */
export function exampleValues(template: Pick<MessageTemplate, 'components'>): TemplateVariableValues {
  const spec = templateVariables(template)
  return {
    header: spec.header.names.map((_, i) => spec.header.examples[i] ?? ''),
    body: spec.body.names.map((_, i) => spec.body.examples[i] ?? ''),
    buttons: Object.fromEntries(spec.buttons.map((button) => [String(button.index), button.example ?? ''])),
  }
}
