import { defineConfig } from 'vite'
import solid from 'vite-plugin-solid'

// Proxy API requests in development
export default defineConfig({
  plugins: [solid()],
  server: {
    proxy: {
      '/api': 'http://localhost:5001' // Change 5001 to your backend port if different
    }
  }
})
