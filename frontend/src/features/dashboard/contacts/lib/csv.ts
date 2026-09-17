/**
 * Client-side CSV reading for the import preview only. The server parses the file for real
 * (`apps/contacts/tasks.py`); these rules mirror its header mapping so the preview is honest.
 */
import type { ImportRowError } from './types'

/** Header names the server accepts for the phone column (case-insensitive). */
export const PHONE_ALIASES = ['phone', 'phone_number', 'mobile', 'whatsapp', 'number'] as const

export const MAX_IMPORT_BYTES = 10 * 1024 * 1024

/**
 * Example file shown and offered for download on the import page. Made-up customers; the columns
 * show each mapping (phone with and without +91, name, email, attributes, a quoted comma).
 */
export const SAMPLE_CSV_FILENAME = 'upchatz-contacts-sample.csv'
export const SAMPLE_CSV = [
  'phone,name,email,city,last_order',
  '+919876543210,Priya Sharma,priya.sharma@example.com,Jaipur,Kaju katli 500 g',
  '9812345678,Rahul Verma,,Pune,"Rasgulla, 1 kg"',
  '+91 99887 76655,Ananya Iyer,ananya@example.com,Chennai,',
].join('\r\n')

export type ColumnTarget = 'phone' | 'name' | 'email' | 'attribute' | 'ignored'

export type ColumnMapping = {
  index: number
  header: string
  target: ColumnTarget
  /** Attribute key for `attribute` columns (the lower-cased header). */
  key: string
}

export type CsvPreview = {
  header: string[]
  /** First data rows (blank rows skipped). */
  rows: string[][]
  /** Non-blank data rows in the whole file. */
  rowCount: number
  mapping: ColumnMapping[]
  hasPhoneColumn: boolean
}

/** RFC 4180-style parser: quoted fields, escaped quotes, CRLF/LF, optional BOM. */
export function parseCsv(text: string, maxRows = Infinity): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  let i = text.charCodeAt(0) === 0xfeff ? 1 : 0

  const endRow = () => {
    row.push(field)
    rows.push(row)
    row = []
    field = ''
  }

  for (; i < text.length; i++) {
    const char = text[i]
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"'
          i++
        } else quoted = false
      } else field += char
      continue
    }
    if (char === '"' && field === '') quoted = true
    else if (char === ',') {
      row.push(field)
      field = ''
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[i + 1] === '\n') i++
      endRow()
      if (rows.length >= maxRows) return rows
    } else field += char
  }
  if (field !== '' || row.length > 0) endRow()
  return rows
}

const isBlank = (row: string[]) => row.every((cell) => !cell.trim())

/** Maps header cells to contact fields the way the server does. */
export function mapColumns(header: string[]): ColumnMapping[] {
  const keys = header.map((cell) => cell.trim().toLowerCase())
  const phone = keys.findIndex((key) => (PHONE_ALIASES as readonly string[]).includes(key))
  const name = keys.indexOf('name')
  const email = keys.indexOf('email')

  return header.map((cell, index) => {
    const key = keys[index]
    let target: ColumnTarget = 'attribute'
    if (index === phone) target = 'phone'
    else if (index === name) target = 'name'
    else if (index === email) target = 'email'
    else if (!key || keys.indexOf(key) < index) target = 'ignored'
    return { index, header: cell.trim(), target, key }
  })
}

export function buildPreview(text: string, previewRows = 5): CsvPreview | null {
  const all = parseCsv(text)
  const headerIndex = all.findIndex((row) => !isBlank(row))
  if (headerIndex !== 0 || !all.length) return null
  const header = all[0]
  const data = all.slice(1).filter((row) => !isBlank(row))
  const mapping = mapColumns(header)
  return {
    header,
    rows: data.slice(0, previewRows),
    rowCount: data.length,
    mapping,
    hasPhoneColumn: mapping.some((column) => column.target === 'phone'),
  }
}

function csvCell(value: string | number | null) {
  const text = value === null ? '' : String(value)
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** The import's error list as a downloadable CSV (`row,error`). */
export function errorsToCsv(errors: readonly ImportRowError[]): string {
  return ['row,error', ...errors.map((error) => `${csvCell(error.row)},${csvCell(error.error)}`)].join('\r\n')
}
