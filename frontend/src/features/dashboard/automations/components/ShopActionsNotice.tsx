import { useFormContext, useWatch } from 'react-hook-form'
import { Link } from 'react-router'
import { useWorkspace } from '../../../../lib/workspace'
import { Notice } from '../../campaigns/components/Notice'
import type { AutomationActionType } from '../api'
import type { RuleFormValues } from '../ruleForm'

const shopActionTypes: readonly AutomationActionType[] = ['send_shop_menu', 'send_catalog', 'send_collection']

/** Shown under the actions when the rule uses a shop action, which only runs while the store is on. */
export function ShopActionsNotice() {
  const { control } = useFormContext<RuleFormValues>()
  const { workspaceId, can } = useWorkspace()
  const actions = useWatch({ control, name: 'actions' })
  if (!actions?.some((action) => shopActionTypes.includes(action.type))) return null
  return (
    <Notice title="Shop actions need your store turned on">
      Send shop menu, Send catalog and Send collection are skipped while the store is off.{' '}
      {can('admin') && (
        <Link to={`/app/w/${workspaceId}/store/settings`} className="text-accent-2 underline underline-offset-4">
          Store settings
        </Link>
      )}
    </Notice>
  )
}
