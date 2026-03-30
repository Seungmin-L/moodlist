import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  timeout: 90_000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use(
  (res) => res,
  (error) => {
    const message =
      error.response?.data?.detail ??
      error.message ??
      '알 수 없는 오류가 발생했습니다'
    return Promise.reject(new Error(message))
  }
)

export default client
