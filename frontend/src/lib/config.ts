// 运行时配置

/// <reference types="vite/client" />

interface AppEnv {
  VITE_API_BASE?: string
}

const env = (import.meta.env ?? {}) as unknown as AppEnv

export const API_BASE = (env.VITE_API_BASE ?? '').replace(/\/$/, '')

export function apiUrl(path: string): string {
  if (!path.startsWith('/')) path = '/' + path
  return `${API_BASE}${path}`
}
