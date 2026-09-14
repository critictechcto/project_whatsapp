import { z } from 'zod'
import { distinctVariables, toTemplateRequest, type BuilderValues } from './builderModel'
import { issueForComponentMessage, type BuilderIssue } from './errorPaths'
import { CATEGORIES, HEADER_TEXT_MAX_LENGTH, languageErrors, nameErrors, textLength, validateTemplate, variableNumbers } from './validate'

const buttonSchema = z.object({
  type: z.enum(['QUICK_REPLY', 'URL', 'PHONE_NUMBER', 'COPY_CODE']),
  text: z.string(),
  url: z.string(),
  urlExample: z.string(),
  phoneNumber: z.string(),
  code: z.string(),
})

/**
 * Friendly, field-level checks first (so each empty input gets its own message), then the full
 * backend rule set from `validate.ts` as a backstop: anything the API would reject is rejected here.
 */
export function builderIssues(values: BuilderValues): BuilderIssue[] {
  const issues: BuilderIssue[] = []
  const add = (path: string, message: string) => issues.push({ path, message })

  const name = nameErrors(values.name)[0]
  if (name) add('name', name)
  const language = languageErrors(values.language)[0]
  if (language) add('language', language)

  if (values.category === 'AUTHENTICATION') {
    const minutes = values.codeExpirationMinutes.trim()
    if (minutes && (!/^\d+$/.test(minutes) || Number(minutes) < 1 || Number(minutes) > 90)) {
      add('codeExpirationMinutes', 'Enter a whole number of minutes from 1 to 90, or leave it empty.')
    }
    if (values.otpType === 'ONE_TAP') {
      if (!values.packageName.trim()) add('packageName', 'Enter your Android app package name.')
      if (!values.signatureHash.trim()) add('signatureHash', "Enter your app's signature hash.")
    }
  } else {
    if (values.headerType === 'TEXT') {
      if (!values.headerText.trim()) add('headerText', 'Enter the header text.')
      else if (textLength(values.headerText) <= HEADER_TEXT_MAX_LENGTH && variableNumbers(values.headerText).length === 1 && !values.headerExample.trim()) {
        add('headerExample', 'Enter an example value for {{1}}.')
      }
    }

    if (!values.bodyText.trim()) {
      add('bodyText', 'Enter the message text.')
    } else {
      const numbers = distinctVariables(values.bodyText)
      const sequential = numbers.every((n, i) => n === i + 1)
      if (sequential) {
        numbers.forEach((n) => {
          if (!values.bodyExamples[n - 1]?.trim()) add(`bodyExamples.${n - 1}`, `Enter an example value for {{${n}}}.`)
        })
      }
    }

    values.buttons.forEach((button, index) => {
      if (button.type === 'COPY_CODE') {
        if (!button.code.trim()) add(`buttons.${index}.code`, 'Enter a sample offer code.')
        return
      }
      if (!button.text.trim()) add(`buttons.${index}.text`, 'Enter the button text.')
      if (button.type === 'URL' && variableNumbers(button.url).length === 1 && button.url.endsWith('{{1}}') && !button.urlExample.trim()) {
        add(`buttons.${index}.urlExample`, 'Enter an example value for {{1}}.')
      }
      if (button.type === 'PHONE_NUMBER' && !button.phoneNumber.trim()) add(`buttons.${index}.phoneNumber`, 'Enter the phone number to call.')
    })
  }

  // Backstop: the exact backend rules on the payload we would send.
  const payload = toTemplateRequest(values)
  const serverStyle = validateTemplate(payload)
  const taken = new Set(issues.map((issue) => issue.path))
  const backstop: BuilderIssue[] = [
    ...(serverStyle.category ?? []).map((message) => ({ path: 'category', message })),
    ...(serverStyle.components ?? []).map((message) => issueForComponentMessage(message, values)),
  ]
  for (const issue of backstop) {
    // Example-list messages are covered by the per-example checks above.
    const covered = taken.has(issue.path) || (issue.path === 'bodyExamples' && [...taken].some((path) => path.startsWith('bodyExamples.')))
    if (covered) continue
    taken.add(issue.path)
    issues.push(issue)
  }
  return issues
}

export const builderSchema = z
  .object({
    waba: z.string().min(1, 'Choose the WhatsApp Business Account for this template.'),
    name: z.string(),
    category: z.enum(CATEGORIES),
    language: z.string(),
    headerType: z.enum(['NONE', 'TEXT', 'IMAGE', 'VIDEO', 'DOCUMENT', 'LOCATION']),
    headerText: z.string(),
    headerExample: z.string(),
    headerHandle: z.string(),
    bodyText: z.string(),
    bodyExamples: z.array(z.string()),
    footerText: z.string(),
    buttons: z.array(buttonSchema),
    addSecurityRecommendation: z.boolean(),
    codeExpirationMinutes: z.string(),
    otpType: z.enum(['COPY_CODE', 'ONE_TAP']),
    otpButtonText: z.string(),
    packageName: z.string(),
    signatureHash: z.string(),
  })
  .superRefine((values, ctx) => {
    for (const issue of builderIssues(values)) {
      ctx.addIssue({
        code: 'custom',
        message: issue.message,
        path: issue.path.split('.').map((part) => (/^\d+$/.test(part) ? Number(part) : part)),
      })
    }
  })
