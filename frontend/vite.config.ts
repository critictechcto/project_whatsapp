import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/** Normalises VITE_BASE to an absolute path with leading and trailing slashes. */
function resolveBase(raw: string | undefined) {
  const value = (raw ?? '').trim()
  if (!value || value === '/') return '/'
  return `/${value.replace(/^\/+|\/+$/g, '')}/`
}

/*
 * Critical fonts for the first screen: Schibsted Grotesk (headings) and IBM Plex Sans (body), latin
 * subset only. They are referenced from Fontsource CSS, so the browser would otherwise find them only
 * after downloading and applying the stylesheet. Hashed names come from the build bundle.
 */
const PRELOAD_FONTS = [
  /schibsted-grotesk-latin-wght-normal(-[\w-]+)?\.woff2$/,
  /ibm-plex-sans-latin-wght-normal(-[\w-]+)?\.woff2$/,
]

function preloadFonts(): Plugin {
  let base = '/'
  return {
    name: 'upchatz:preload-fonts',
    apply: 'build',
    configResolved(config) {
      base = config.base
    },
    transformIndexHtml: {
      order: 'post',
      handler(_html, { bundle }) {
        if (!bundle) return
        const files = Object.values(bundle)
          .filter((item) => item.type === 'asset')
          .map((item) => item.fileName)
        return PRELOAD_FONTS.flatMap((pattern) => {
          const fileName = files.find((file) => pattern.test(file))
          if (!fileName) throw new Error(`preload-fonts: no bundled font matches ${pattern}`)
          return [
            {
              tag: 'link',
              attrs: { rel: 'preload', href: `${base}${fileName}`, as: 'font', type: 'font/woff2', crossorigin: '' },
              injectTo: 'head' as const,
            },
          ]
        })
      },
    },
  }
}

export default defineConfig(({ mode, isSsrBuild }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')

  return {
    // Absolute base so deep links like /app/w/<id>/inbox resolve assets correctly.
    // GitHub Pages (project site) builds with VITE_BASE=/<repo>/; a custom domain uses '/'.
    base: resolveBase(env.VITE_BASE ?? process.env.VITE_BASE),
    plugins: [react(), tailwindcss(), preloadFonts()],
    // No manualChunks: grouping recharts/msw pulled shared deps (React) into those groups and made
    // the landing entry import them. Dynamic imports alone keep the dashboard, charts
    // (components/app/charts/LazyTrendChart) and MSW (App.tsx, mock mode only) out of the landing bundle.
    build: {
      // The SSR build (scripts/prerender.mjs) only needs entry-server.js, not a second copy of public/.
      copyPublicDir: !isSsrBuild,
      // three.js alone is ~520 kB minified and cannot be split further; it lives only in the lazy
      // scroll-story chunk (StoryCanvas, ~140 kB gzip), which desktops fetch near that section.
      chunkSizeWarningLimit: 600,
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              {
                // Mock builds only: MSW's own packages (tldts alone is ~245 kB of public-suffix data)
                // made the mock worker chunk ~590 kB. This group lists MSW's dependency tree and
                // nothing shared, and does not follow dependencies, so React stays where it was.
                name: 'msw',
                test: /[\\/]node_modules[\\/](msw|@mswjs[\\/][^\\/]+|tough-cookie|tldts|tldts-core|path-to-regexp|rettime|@open-draft[\\/][^\\/]+|set-cookie-parser|headers-polyfill|strict-event-emitter|outvariant|is-node-process|until-async|cookie|graphql|statuses|type-fest|picocolors)[\\/]/,
                includeDependenciesRecursively: false,
              },
            ],
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
      // jsdom tests are CPU-bound. The default (all logical cores but one) oversubscribes
      // hyperthreads: on a 10-core/16-thread machine it spent twice the CPU for no wall-clock gain
      // and pushed findBy waits past their timeouts. Forks, not threads: worker startup with
      // threads was ~4x slower here.
      maxWorkers: '50%',
      // Dashboard tests render whole routed pages and lazy chunks; the full parallel suite on a
      // loaded machine needs far more than the 5 s default.
      testTimeout: 30_000,
      env: {
        VITE_API_MODE: 'live',
        VITE_API_URL: 'http://localhost:3000',
        VITE_WS_URL: 'ws://localhost:3000',
      },
    },
  }
})
