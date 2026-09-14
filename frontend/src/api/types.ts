import type { components, paths } from './schema'

/** All OpenAPI component schemas, e.g. `Schemas['Workspace']`. */
export type Schemas = components['schemas']

export type Me = Schemas['Me']
export type Workspace = Schemas['Workspace']
export type Membership = Schemas['Membership']
export type Invitation = Schemas['Invitation']
export type MessageTemplate = Schemas['MessageTemplate']
export type TemplateStatus = Schemas['MessageTemplateStatusEnum']
export type TemplateCategory = Schemas['MessageTemplateCategoryEnum']
export type PhoneNumber = Schemas['PhoneNumber']
export type Contact = Schemas['Contact']
export type Tag = Schemas['Tag']
export type SignupConfig = Schemas['SignupConfig']
export type EmbeddedSignupRequest = Schemas['EmbeddedSignupRequest']
export type RoleEnum = Schemas['RoleEnum']

/** Cursor-paginated list body: `{ next, previous, results }`. */
export type CursorPage<T> = {
  next?: string | null
  previous?: string | null
  results: T[]
}

/*
 * The generated schema marks `X-Workspace-ID` as a required header on tenant endpoints.
 * The client injects it from the active route workspace, so the typed client makes it optional.
 */
type WorkspaceHeader = { 'X-Workspace-ID': string }

type RelaxHeader<H> = [H] extends [WorkspaceHeader]
  ? Omit<H, 'X-Workspace-ID'> & { 'X-Workspace-ID'?: string }
  : H

type RelaxParameters<P> = P extends { header: infer H }
  ? Omit<P, 'header'> & { header?: RelaxHeader<H> }
  : P

type RelaxOperation<O> = O extends { parameters: infer P }
  ? Omit<O, 'parameters'> & { parameters: RelaxParameters<P> }
  : O

/** `paths` with the workspace header optional on every operation. Used by the `api` client. */
export type AppPaths = {
  [Path in keyof paths]: {
    [Key in keyof paths[Path]]: Key extends 'parameters' ? paths[Path][Key] : RelaxOperation<paths[Path][Key]>
  }
}
