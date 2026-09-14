import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'
import {
  Button,
  Combobox,
  Field,
  Select,
  Textarea,
  TemplatePicker,
  templateVariables,
  WhatsAppMessagePreview,
} from '../../../../components/app'
import { useWorkspace } from '../../../../lib/workspace'
import { VariableSourceFields } from '../../campaigns/components/VariableSourceFields'
import { defaultBodySource } from '../../campaigns/variables'
import { useTagOptions, useTemplate } from '../../campaigns/wizard/queries'
import { actionLabels, useMembers, type AutomationActionType } from '../api'
import { actionTypes, emptyAction, type RuleFormValues } from '../ruleForm'

type ActionCardProps = {
  index: number
  count: number
  onMove: (to: number) => void
  onRemove: () => void
  readOnly: boolean
}

export function ActionCard({ index, count, onMove, onRemove, readOnly }: ActionCardProps) {
  const {
    control,
    register,
    setValue,
    formState: { errors, isSubmitted },
  } = useFormContext<RuleFormValues>()
  const { workspaceId } = useWorkspace()
  const type = useWatch({ control, name: `actions.${index}.type` })
  const text = useWatch({ control, name: `actions.${index}.text` })
  const templateId = useWatch({ control, name: `actions.${index}.template_id` })
  const tags = useTagOptions(workspaceId)
  const members = useMembers(workspaceId)
  const template = useTemplate(workspaceId, type === 'send_template' && templateId ? templateId : undefined)
  const actionErrors = errors.actions?.[index]
  const position = index + 1
  const bodyNames = type === 'send_template' && template.data ? templateVariables(template.data).body.names : []

  return (
    <li className="rounded-xl border border-line bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-2 px-4 py-2.5">
        <h3 className="font-mono text-[12px] uppercase tracking-[0.12em] text-muted">Action {position}</h3>
        {!readOnly && (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Move action ${position} up`}
              icon={<ArrowUp className="size-4" aria-hidden="true" />}
              disabled={index === 0}
              onClick={() => onMove(index - 1)}
            />
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Move action ${position} down`}
              icon={<ArrowDown className="size-4" aria-hidden="true" />}
              disabled={index === count - 1}
              onClick={() => onMove(index + 1)}
            />
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Remove action ${position}`}
              icon={<Trash2 className="size-4" aria-hidden="true" />}
              disabled={count <= 1}
              onClick={onRemove}
            />
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4 p-4">
        <Field label="Do this">
          <Select
            value={type}
            options={actionTypes.map((value) => ({ value, label: actionLabels[value] }))}
            onChange={(event) =>
              setValue(`actions.${index}`, emptyAction(event.target.value as AutomationActionType), { shouldDirty: true })
            }
          />
        </Field>

        {type === 'send_text' && (
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_260px]">
            <Field label="Message" hint="WhatsApp formatting works: *bold*, _italic_." error={actionErrors?.text?.message} required>
              <Textarea rows={5} maxLength={4096} {...register(`actions.${index}.text`)} />
            </Field>
            <div aria-label={`Preview of action ${position}`} role="group">
              <p className="mb-1.5 text-[13px] font-medium text-ink">Preview</p>
              <WhatsAppMessagePreview message={{ body: text || 'Your message appears here.' }} />
            </div>
          </div>
        )}

        {type === 'send_template' && (
          <>
            <Field label="Template" hint="Approved templates can be sent even after the 24-hour window has closed." error={actionErrors?.template_id?.message} required>
              <TemplatePicker
                value={templateId || null}
                disabled={readOnly}
                onChange={(selected) => {
                  setValue(`actions.${index}.template_id`, selected?.id ?? '', { shouldDirty: true, shouldValidate: isSubmitted })
                  setValue(
                    `actions.${index}.body_params`,
                    selected ? templateVariables(selected).body.names.map((_, position) => defaultBodySource(position)) : [],
                    { shouldDirty: true },
                  )
                }}
              />
            </Field>
            {bodyNames.map((name, position) => (
              <Controller
                key={name}
                control={control}
                name={`actions.${index}.body_params.${position}`}
                render={({ field }) => (
                  <VariableSourceFields
                    label={`Body {{${name}}}`}
                    value={field.value}
                    onChange={field.onChange}
                    disabled={readOnly}
                    errors={{
                      value: actionErrors?.body_params?.[position]?.value?.message,
                      fallback: actionErrors?.body_params?.[position]?.fallback?.message,
                    }}
                  />
                )}
              />
            ))}
          </>
        )}

        {type === 'add_tags' && (
          <Field label="Tags" error={actionErrors?.tag_ids?.message} required>
            <Controller
              control={control}
              name={`actions.${index}.tag_ids`}
              render={({ field }) => (
                <Combobox
                  multiple
                  value={field.value}
                  onChange={field.onChange}
                  options={(tags.data ?? []).map((tag) => ({ value: tag.id, label: tag.name }))}
                  loading={tags.isPending}
                  disabled={readOnly}
                  placeholder="Choose tags"
                  emptyText="No tags yet. Create them on the Contacts page."
                />
              )}
            />
          </Field>
        )}

        {type === 'assign' && (
          <Field label="Assign to" error={actionErrors?.user_id?.message} required>
            <Select
              {...register(`actions.${index}.user_id`)}
              placeholder="Choose a team member"
              options={(members.data ?? []).map((member) => ({ value: member.user.id, label: member.user.full_name || member.user.email }))}
            />
          </Field>
        )}

        {type === 'close_conversation' && (
          <p className="text-sm text-muted">Closes the conversation. It opens again when the customer writes back.</p>
        )}
      </div>
    </li>
  )
}
