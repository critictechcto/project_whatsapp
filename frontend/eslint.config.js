import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import { reactRefresh } from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'public/mockServiceWorker.js', 'src/api/schema.d.ts']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, tseslint.configs.recommended, reactHooks.configs.flat.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['src/**/*.tsx'],
    extends: [reactRefresh.configs.vite()],
    ignores: ['src/**/*.test.tsx', 'src/test/**'],
  },
  {
    // Landing code predates react-hooks v7's compiler rules. Its synchronous setState in effects is
    // the intended reduced-motion "jump to final state" path, so the rule is relaxed only there.
    files: ['src/features/landing/**/*.{ts,tsx}', 'src/lib/useCountUp.ts', 'src/lib/useInView.ts'],
    rules: { 'react-hooks/set-state-in-effect': 'off' },
  },
  {
    files: ['*.config.{js,ts}'],
    languageOptions: { globals: globals.node },
  },
])
