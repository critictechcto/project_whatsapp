import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Lock, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { api, unwrap } from '../../../../api/client'
import { ApiError, errorMessage } from '../../../../api/errors'
import type { Schemas } from '../../../../api/types'
import { Button, EmptyState, PageHeader, PageSpinner, useToast } from '../../../../components/app'
import { useWorkspace } from '../../../../lib/workspace'
import { KeywordChipsInput } from '../../automations/components/KeywordChipsInput'
import { contactKeys } from '../api'
import { normalizeKeyword } from '../lib/consent'
import { FormError } from '../components/shared'

type ConsentKeywords = Schemas['ConsentKeywords']
type Lists = Pick<ConsentKeywords, 'opt_in_keywords' | 'opt_out_keywords'>

const MAX_WORDS = 20
const MAX_LENGTH = 40

function fieldError(error: unknown, field: keyof Lists): string | undefined {
  if (!(error instanceof ApiError) || typeof error.details !== 'object' || error.details === null) return undefined
  const messages = (error.details as Record<string, unknown>)[field]
  return Array.isArray(messages) && typeof messages[0] === 'string' ? messages[0] : undefined
}

export function ConsentKeywordsPage() {
  const { workspaceId, can } = useWorkspace()
  const keywords = useQuery({
    queryKey: contactKeys.custom(workspaceId, 'consent-keywords'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/contacts/consent-keywords/', { signal })),
  })

  return (
    <div className="flex flex-col gap-6">
      <Link to={`/app/w/${workspaceId}/contacts`} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden="true" />
        Contacts
      </Link>
      <PageHeader
        title="Consent keywords"
        description="When a customer sends one of these words as their whole message on WhatsApp, their marketing consent is recorded on the contact, with the message as proof."
      />
      {keywords.isError ? (
        <EmptyState
          icon={<TriangleAlert />}
          title="Consent keywords didn't load"
          action={
            <Button variant="secondary" onClick={() => void keywords.refetch()}>
              Try again
            </Button>
          }
        />
      ) : keywords.data ? (
        <KeywordsForm key={keywords.data.updated_at} saved={keywords.data} canEdit={can('admin')} />
      ) : (
        <PageSpinner />
      )}
    </div>
  )
}

function KeywordsForm({ saved, canEdit }: { saved: ConsentKeywords; canEdit: boolean }) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [optIn, setOptIn] = useState<string[]>(saved.opt_in_keywords)
  const [optOut, setOptOut] = useState<string[]>(saved.opt_out_keywords)
  const locked = saved.locked_opt_out_keywords
  const dirty = optIn.join('\n') !== saved.opt_in_keywords.join('\n') || optOut.join('\n') !== saved.opt_out_keywords.join('\n')

  const save = useMutation({
    mutationFn: (body: Lists) => unwrap(api.PATCH('/api/v1/contacts/consent-keywords/', { body })),
    onSuccess: (data) => {
      queryClient.setQueryData(contactKeys.custom(workspaceId, 'consent-keywords'), data)
      toast({ title: 'Consent keywords saved', tone: 'success' })
    },
  })

  const validate = (list: 'in' | 'out') => (word: string) => {
    if (word.length > MAX_LENGTH) return `Keep each word under ${MAX_LENGTH} characters.`
    if (locked.includes(word)) return list === 'in' ? `“${word}” always opts out.` : `“${word}” is already an opt-out word.`
    if (list === 'in' && optOut.includes(word)) return `“${word}” is an opt-out word. Use it in one list only.`
    if (list === 'out' && optIn.includes(word)) return `“${word}” is an opt-in word. Use it in one list only.`
    return null
  }

  const defaults = saved.default_opt_in_keywords
  const isDefaultOptIn = optIn.length === defaults.length && defaults.every((word) => optIn.includes(word))

  return (
    <form
      noValidate
      className="flex max-w-2xl flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate({ opt_in_keywords: optIn, opt_out_keywords: optOut })
      }}
    >
      <FormError message={save.isError && !fieldError(save.error, 'opt_in_keywords') && !fieldError(save.error, 'opt_out_keywords') ? errorMessage(save.error) : undefined} />

      <section className="flex flex-col gap-3 rounded-xl border border-line bg-card p-4">
        <h2 className="font-display text-base font-semibold text-ink">Opt in</h2>
        <KeywordChipsInput
          label="Opt-in words"
          itemName="opt-in word"
          placeholder="haan"
          value={optIn}
          onChange={setOptIn}
          max={MAX_WORDS}
          normalize={normalizeKeyword}
          validate={validate('in')}
          disabled={!canEdit}
          error={fieldError(save.error, 'opt_in_keywords')}
          hint="Use words in your customers' language, such as haan or offers. Leave empty to collect opt-ins only with the opt-in button automation."
        />
        {canEdit && !isDefaultOptIn && (
          <Button variant="ghost" size="sm" className="self-start" onClick={() => setOptIn([...defaults])}>
            Reset to {defaults.map((word) => word.toUpperCase()).join(' and ')}
          </Button>
        )}
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-line bg-card p-4">
        <h2 className="font-display text-base font-semibold text-ink">Opt out</h2>
        <div className="flex flex-col gap-1.5">
          <p className="text-[13px] font-medium text-ink">Always on</p>
          <ul aria-label="Opt-out words that always apply" className="flex flex-wrap gap-1.5">
            {locked.map((word) => (
              <li key={word} className="inline-flex items-center gap-1 rounded-full bg-ink/5 px-2.5 py-0.5 font-mono text-[12px] text-ink-2">
                <Lock className="size-3" aria-hidden="true" />
                {word}
              </li>
            ))}
          </ul>
          <p className="text-[12.5px] text-muted">Customers expect STOP to work, so these can't be removed.</p>
        </div>
        <KeywordChipsInput
          label="Extra opt-out words"
          itemName="opt-out word"
          placeholder="band karo"
          value={optOut}
          onChange={setOptOut}
          max={MAX_WORDS}
          normalize={normalizeKeyword}
          validate={validate('out')}
          disabled={!canEdit}
          error={fieldError(save.error, 'opt_out_keywords')}
        />
      </section>

      <p className="text-[13px] text-muted">
        Only a whole message counts: “stop” inside a longer sentence changes nothing. Case and trailing punctuation are ignored.
      </p>

      {canEdit ? (
        <Button type="submit" className="self-start" loading={save.isPending} disabled={!dirty}>
          Save keywords
        </Button>
      ) : (
        <p className="text-sm text-muted">Only admins can change consent keywords.</p>
      )}
    </form>
  )
}
