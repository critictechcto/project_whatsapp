# Onboarding contract

The backend (`apps.tenants`) implements this; the dashboard area `features/dashboard/onboarding` and the Home checklist consume it. Conventions from `docs/contracts/wave-2.md` apply (errors, roles, `X-Workspace-ID`). Adding optional response fields is allowed; anything else needs a lead request.

## State

- **Workspace goals** `Workspace.business_goals`: a list of `sell` | `marketing` | `support`, stored in that order without repeats; empty until chosen. One list per workspace; it orders the Home checklist for everyone.
- **Per-person flags** on `Membership` (one person in one workspace): `welcome_completed_at`, `tour_completed_at`, `checklist_dismissed_at`. Null means not done.
- Memberships that existed before onboarding shipped are marked welcomed by migration `tenants.0002_onboarding`, so only new members see the welcome flow.

## `GET /api/v1/workspaces/onboarding/` → `Onboarding`

Any member (viewer and up). Non-members get 404 `workspace_not_found`; a missing header gives 400 `workspace_required`.

| Field | Type |
|---|---|
| `goals` | list of `WorkspaceGoalEnum` (fixed order sell, marketing, support) |
| `welcome_completed` | boolean |
| `tour_completed` | boolean |
| `checklist_dismissed` | boolean |
| `can_set_goal` | boolean, read-only: the caller is admin or owner |

## `PATCH /api/v1/workspaces/onboarding/` (`PatchedOnboardingRequest`) → `Onboarding`

Any member, all fields optional:

- `welcome_completed`, `tour_completed`, `checklist_dismissed`: the caller's own flags. `true` stamps the time (kept if already set), `false` clears it — that is how "Take the tour" and "Show setup guide" replay.
- `goals`: replaces the whole list (`[]` clears it; repeats are dropped and the order is normalised). Admins and owners only, otherwise 403 `insufficient_role` and nothing in the request is applied. An unknown value is 400 with `details.goals`.

## Dashboard behaviour

- The welcome flow shows when `welcome_completed` is false; skipping or finishing PATCHes `welcome_completed: true`. The goal step (several choices allowed) shows only when `can_set_goal`. Its last page has one button, *Take a quick tour*, which ends the flow and starts the tour.
- The tour PATCHes `tour_completed: true` when finished or skipped; the user menu's "Take the tour" starts it again.
- "Hide checklist" PATCHes `checklist_dismissed: true`; the user menu's "Show setup guide" PATCHes `false`.
- Home checklist order: the first steps of each chosen goal (in goal order), then the rest of each chosen goal's list, without repeats. Per goal:
  - `sell`: Connect WhatsApp → Add products → Set up payments → Turn on your store (store steps from `GET /api/v1/store/checklist/`)
  - `marketing`: Connect WhatsApp → Add contacts → Create a template → Send a first campaign → Automation → Team
  - `support`: Connect WhatsApp → Invite your team → Set up an automation → Add contacts
  - none chosen: the existing order (WhatsApp, contacts, templates, campaigns, automations, team).
