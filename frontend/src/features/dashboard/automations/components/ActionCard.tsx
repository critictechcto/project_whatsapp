import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'
import { Link } from 'react-router'
import {
  Button,
  Combobox,
  Field,
  InteractiveMessagePreview,
  Input,
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
import { actionLabels, useCollections, useMembers, type AutomationActionType } from '../api'
import {
  actionTypes,
  DEFAULT_CONFIRMATION,
  DEFAULT_NO_LABEL,
  DEFAULT_YES_LABEL,
  emptyAction,
  MAX_BUTTON_LABEL,
  MAX_OPT_IN_TEXT,
  type RuleFormValues,
} from '../ruleForm'

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
  const yesLabel = useWatch({ control, name: `actions.${index}.yes_label` })
  const noLabel = useWatch({ control, name: `actions.${index}.no_label` })
  const tags = useTagOptions(workspaceId)
  const members = useMembers(workspaceId)
  const collections = useCollections(workspaceId, type === 'send_collection')
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

        {type === 'send_shop_menu' && (
          <p className="text-sm text-muted">
            Sends your store's welcome menu with Shop now, My orders and Talk to us buttons, so the customer can start shopping in the chat.
          </p>
        )}

        {type === 'send_catalog' && (
          <p className="text-sm text-muted">
            Sends your products to browse: collection menus, or your WhatsApp catalog if the store uses it. The customer can add items to a
            cart and check out.
          </p>
        )}

        {type === 'send_collection' && (
          <Field
            label="Collection"
            hint="Sends the products in this collection as a list the customer can pick from."
            error={actionErrors?.collection_id?.message}
            required
          >
            {collections.data && collections.data.length === 0 ? (
              <p className="text-sm text-muted">
                No collections yet.{' '}
                <Link to={`/app/w/${workspaceId}/catalog`} className="text-accent-2 underline underline-offset-4">
                  Create one in Catalog
                </Link>
              </p>
            ) : (
              <Select
                {...register(`actions.${index}.collection_id`)}
                disabled={readOnly || collections.isPending}
                placeholder={collections.isPending ? 'Loading collections…' : 'Choose a collection'}
                options={(collections.data ?? []).map((collection) => ({
                  value: collection.id,
                  label: collection.is_active ? collection.name : `${collection.name} (hidden)`,
                }))}
              />
            )}
          </Field>
        )}

        {type === 'send_opt_in_request' && (
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_260px]">
            <div className="flex flex-col gap-4">
              <p className="text-sm text-muted">
                Asks for marketing consent with two buttons. A tap on the first records an opt-in on the contact, with the time and the
                message as proof, so campaigns can send them marketing templates.
              </p>
              <Field label="Question" error={actionErrors?.text?.message} required>
                <Textarea rows={3} maxLength={MAX_OPT_IN_TEXT} {...register(`actions.${index}.text`)} />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Opt-in button" hint={`Up to ${MAX_BUTTON_LABEL} characters.`} error={actionErrors?.yes_label?.message} required>
                  <Input maxLength={MAX_BUTTON_LABEL} {...register(`actions.${index}.yes_label`)} />
                </Field>
                <Field label="Decline button" hint={`Up to ${MAX_BUTTON_LABEL} characters.`} error={actionErrors?.no_label?.message} required>
                  <Input maxLength={MAX_BUTTON_LABEL} {...register(`actions.${index}.no_label`)} />
                </Field>
              </div>
              <Field label="Reply after opting in" hint="Leave empty to use the default." error={actionErrors?.confirmation_text?.message}>
                <Textarea rows={2} maxLength={4096} placeholder={DEFAULT_CONFIRMATION} {...register(`actions.${index}.confirmation_text`)} />
              </Field>
              <Field label="Reply after declining" hint="Leave empty to send nothing." error={actionErrors?.decline_text?.message}>
                <Textarea rows={2} maxLength={4096} {...register(`actions.${index}.decline_text`)} />
              </Field>
            </div>
            <div aria-label={`Preview of action ${position}`} role="group">
              <p className="mb-1.5 text-[13px] font-medium text-ink">Preview</p>
              <InteractiveMessagePreview
                message={{
                  type: 'button',
                  body: { text: text || 'Your question appears here.' },
                  action: {
                    buttons: [
                      { type: 'reply', reply: { id: 'yes', title: yesLabel || DEFAULT_YES_LABEL } },
                      { type: 'reply', reply: { id: 'no', title: noLabel || DEFAULT_NO_LABEL } },
                    ],
                  },
                }}
              />
            </div>
          </div>
        )}

        {type === 'close_conversation' && (
          <p className="text-sm text-muted">Closes the conversation. It opens again when the customer writes back.</p>
        )}
      </div>
    </li>
  )
}
