# frontend

React + Vite + TypeScript + Tailwind CSS v4.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production build into dist/
```

## Structure

- `src/config/site.ts` — brand name, contact details, navigation, pricing plans. **Change the placeholder brand here** (also update `<title>`/meta tags in `index.html`, `public/favicon.svg`, `public/og-image.svg`).
- `src/components/ui/` — small shared UI primitives (Button, Tabs, Accordion…)
- `src/features/landing/` — marketing landing page: `sections/` (one file per page section) and `mockups/` (product UI illustrations built in HTML/CSS)
- `src/features/dashboard/` — the app UI (not built yet)

Design tokens (colours, fonts) live in the `@theme` block of `src/index.css`.
