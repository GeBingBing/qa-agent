// ThinkingPanel — DeepSeek 风格的思考过程折叠面板

import { memo, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2, Sparkles } from 'lucide-react'

interface Props {
  thinking: string
  active: boolean
}

export const ThinkingPanel = memo(function ThinkingPanel({ thinking, active }: Props) {
  const [open, setOpen] = useState(true)

  // 思考完成后自动收起，让出空间给最终回答
  useEffect(() => {
    if (!active && thinking) setOpen(false)
  }, [active, thinking])

  if (!thinking) return null

  return (
    <div className="rounded-md border border-border bg-secondary/20 text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-muted-foreground transition hover:text-foreground"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {active ? (
          <Loader2 className="h-3 w-3 animate-spin text-primary" />
        ) : (
          <Sparkles className="h-3 w-3 text-primary" />
        )}
        <span className="font-medium">
          {active ? '思考中…' : '已完成思考'}
        </span>
        <span className="ml-auto text-[10px] text-muted-foreground">
          {thinking.length} 字
        </span>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2 text-[11px] leading-relaxed whitespace-pre-wrap text-muted-foreground">
          {thinking}
        </div>
      )}
    </div>
  )
})
