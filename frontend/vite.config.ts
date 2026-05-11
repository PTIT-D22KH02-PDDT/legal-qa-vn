import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8001',
          changeOrigin: true,
          secure: false,
          headers: {
            // Đánh lừa Cloudflare đây là request từ terminal (curl) để không bị chặn bởi trang cảnh báo
            'User-Agent': 'curl/7.68.0' 
          }
        }
      }
    }
  }
})
