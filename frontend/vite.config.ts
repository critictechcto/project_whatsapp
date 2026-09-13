import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  // Relative asset URLs so the same build works at a domain root or under a
  // GitHub Pages project path (https://<user>.github.io/<repo>/).
  base: './',
  plugins: [react(), tailwindcss()],
})
