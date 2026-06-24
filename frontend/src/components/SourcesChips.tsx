// SourcesChips — RAG 命中的来源 chip 列表
// 后端 `/v1/chat` 在 plan 之后、首个 answer_delta / step_start 之前发出 `sources` 事件。
// 每条 chip 显示 [i] source#heading，点击展开 snippet。

import { memo, useState } from 'react'
import type { Source } from '@/types/chat'
import { FileText, ChevronDown } from 'lucide-react'

interface Props {
  sources: Source[]
}

function SourcesChipsImpl({ sources }: Props) {
  const [openId, setOpenId] = useState<number | null>(null)
  if (!sources || sources.length === 0) return null
  return (
    <div className="space-y-1" data-testid="sources-chips">
      <div className="flex flex-wrap gap-1.5">
        {sources.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setOpenId(openId === s.id ? null : s.id)}
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              openId === s.id
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-secondary/50 text-foreground hover:bg-secondary/80'
            }`}
            title={s.heading_path ? `${s.source}#${s.heading_path}` : s.source}
          >
            <FileText className="h-3 w-3" />
            <span className="font-mono text-[10px] text-muted-foreground">[{s.id}]</span>
            <span className="font-medium">{s.source}</span>
            {s.heading_path && (
              <span className="text-muted-foreground">#{s.heading_path}</span>
            )}
            <ChevronDown
              className={`h-3 w-3 transition-transform ${openId === s.id ? 'rotate-180' : ''}`}
            />
          </button>
        ))}
      </div>
      {openId !== null && (() => {
        const src = sources.find((s) => s.id === openId)
        if (!src) return null
        return (
          <div className="rounded-md border border-border bg-card/60 px-3 py-2 text-[12px] leading-relaxed text-muted-foreground">
            <div className="mb-1 font-mono text-[10px] text-muted-foreground">
              [{src.id}] {src.source}{src.heading_path ? `#${src.heading_path}` : ''} · score={src.score.toFixed(4)}
            </div>
            <div className="whitespace-pre-wrap text-foreground">{src.snippet}</div>
          </div>
        )
      })()}
    </div>
  )
}

export const SourcesChips = memo(SourcesChipsImpl)
