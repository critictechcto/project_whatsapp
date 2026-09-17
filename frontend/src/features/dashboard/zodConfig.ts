import { z } from 'zod'

/*
 * The built pages run under a Content-Security-Policy without 'unsafe-eval' (scripts/csp.mjs).
 * Zod's object parser otherwise probes `new Function('')` to decide whether to compile fast
 * parsers; the probe is caught, but the browser still reports a CSP violation. Jitless mode skips
 * the probe and parses with the interpreter. App.tsx imports this before the dashboard and the mock
 * worker load, so no schema parses earlier.
 */
z.config({ jitless: true })
