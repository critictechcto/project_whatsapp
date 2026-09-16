/** Brand tokens for the WebGL scene, read from the `@theme` custom properties in index.css. */
export type StoryTheme = {
  paper: string
  paper2: string
  card: string
  ink: string
  ink2: string
  muted: string
  line: string
  line2: string
  accent: string
  accent2: string
  accentSoft: string
  bubble: string
  wallpaper: string
  amber: string
  amberSoft: string
  sans: string
  mono: string
  display: string
}

const defaults: StoryTheme = {
  paper: '#f6f3ec',
  paper2: '#efeadf',
  card: '#fbfaf6',
  ink: '#10271f',
  ink2: '#1d3a30',
  muted: '#5c6a63',
  line: '#ddd6c7',
  line2: '#e8e2d5',
  accent: '#1d7f55',
  accent2: '#16663f',
  accentSoft: '#dcebdf',
  bubble: '#dff3d8',
  wallpaper: '#ece6d8',
  amber: '#8a5d0c',
  amberSoft: '#f3e8cf',
  sans: "'IBM Plex Sans Variable', system-ui, sans-serif",
  mono: "'IBM Plex Mono', ui-monospace, monospace",
  display: "'Schibsted Grotesk Variable', 'Helvetica Neue', Arial, sans-serif",
}

const tokens: Record<keyof StoryTheme, string> = {
  paper: '--color-paper',
  paper2: '--color-paper-2',
  card: '--color-card',
  ink: '--color-ink',
  ink2: '--color-ink-2',
  muted: '--color-muted',
  line: '--color-line',
  line2: '--color-line-2',
  accent: '--color-accent',
  accentSoft: '--color-accent-soft',
  accent2: '--color-accent-2',
  bubble: '--color-bubble',
  wallpaper: '--color-wallpaper',
  amber: '--color-amber',
  amberSoft: '--color-amber-soft',
  sans: '--font-sans',
  mono: '--font-mono',
  display: '--font-display',
}

export function readTheme(): StoryTheme {
  const style = getComputedStyle(document.documentElement)
  const theme = { ...defaults }
  for (const key of Object.keys(tokens) as (keyof StoryTheme)[]) {
    const value = style.getPropertyValue(tokens[key]).trim()
    if (value) theme[key] = value
  }
  return theme
}

/** Loads the weights the textures use, so the first draw is not in a fallback font. */
export async function loadThemeFonts(theme: StoryTheme) {
  if (typeof document === 'undefined' || !document.fonts) return
  try {
    await Promise.all([
      document.fonts.load(`400 16px ${theme.sans}`),
      document.fonts.load(`600 16px ${theme.sans}`),
      document.fonts.load(`500 16px ${theme.mono}`),
      document.fonts.load(`600 16px ${theme.display}`),
    ])
    await document.fonts.ready
  } catch {
    // Draw with whatever is available.
  }
}
