import { defineConfig } from 'vite'
import solid from 'vite-plugin-solid'

// Proxy API requests in development
export default defineConfig({
  plugins: [solid()],
  server: {
    proxy: {
      '/api': 'http://localhost:3000'
    }
  }
})
