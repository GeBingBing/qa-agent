// 极简 Toast — 全局通知，避免把网络错误硬塞到对话气泡里

import { create } from 'zustand'
import { useEffect } from 'react'
import { X } from 'lucide-react'

interface Toast {
  id: string
  level: 'info' | 'error' | 'success'
  text: string
  ttl: number
}

interface ToastState {
  toasts: Toast[]
  push: (level: Toast['level'], text: string, ttlMs?: number) => string
  dismiss: (id: string) => void
}

const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (level, text, ttlMs = 4000) => {
    const id =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `t-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    set((s) => ({ toasts: [...s.toasts, { id, level, text, ttl: ttlMs }] }))
    return id
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

export const toast = {
  info: (text: string, ttl?: number) => useToastStore.getState().push('info', text, ttl),
  error: (text: string, ttl?: number) => useToastStore.getState().push('error', text, ttl),
  success: (text: string, ttl?: number) => useToastStore.getState().push('success', text, ttl),
}

export function ToastViewport() {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  useEffect(() => {
    if (toasts.length === 0) return
    const timers = toasts.map((t) => window.setTimeout(() => dismiss(t.id), t.ttl))
    return () => {
      timers.forEach((t) => window.clearTimeout(t))
    }
  }, [toasts, dismiss])

  if (toasts.length === 0) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-2 rounded-md border px-3 py-2 text-sm shadow-lg ${
            t.level === 'error'
              ? 'border-rose-500/40 bg-rose-500/10 text-rose-100'
              : t.level === 'success'
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
              : 'border-border bg-card text-foreground'
          }`}
        >
          <span className="flex-1 whitespace-pre-wrap">{t.text}</span>
          <button
            type="button"
            aria-label="关闭"
            onClick={() => dismiss(t.id)}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  )
}
