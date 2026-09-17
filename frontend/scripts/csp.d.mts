// Types for scripts/csp.mjs (imported by src/csp.test.ts).
export type Directives = Record<string, string[]>
export type CspEnv = Record<string, string | undefined>

export const THIRD_PARTY: Record<string, Partial<Record<'script' | 'frame' | 'connect' | 'img', string[]>>>
export function parseOrigins(value: string | undefined, name: string): string[]
export function buildDirectives(env: CspEnv, scriptHashes: string[]): Directives
export function serializePolicy(directives: Directives): string
export function inlineScriptHashes(html: string): string[]
export function injectCsp(html: string, env: CspEnv): string
export function verifyCsp(html: string): Directives
