// 助手 / 用户消息底部的小操作条：复制 / 重发 / 编辑

import { Copy, RefreshCw, Pencil } from 'lucide-react'
import { toast } from './Toast'

interface CopyButtonProps {
  text: string
  label?: string
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through */
  }
  // 降级：用临时 textarea
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

export function CopyButton({ text, label = '复制' }: CopyButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={async () => {
        if (!text) return
        const ok = await copyToClipboard(text)
        if (ok) toast.success('已复制', 2000)
        else toast.error('复制失败：浏览器拒绝访问剪贴板')
      }}
      className="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[11px] text-muted-foreground transition hover:bg-secondary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Copy className="h-3 w-3" />
      {label}
    </button>
  )
}

interface ActionButtonProps {
  label: string
  icon: 'retry' | 'edit'
  onClick: () => void
  disabled?: boolean
}

export function ActionButton({ label, icon, onClick, disabled }: ActionButtonProps) {
  const Icon = icon === 'retry' ? RefreshCw : Pencil
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[11px] text-muted-foreground transition hover:bg-secondary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Icon className="h-3 w-3" />
      {label}
    </button>
  )
}
