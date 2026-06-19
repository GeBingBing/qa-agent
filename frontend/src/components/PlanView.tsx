// PlanView — 渲染 DAG 计划

import { memo } from 'react'
import type { PlanEvent, PlanNode } from '@/types/chat'
import { Badge } from './ui/badge'
import { cn } from '@/lib/utils'

interface Props {
  plan: PlanEvent
}

const kindIcons: Record<PlanNode['kind'], string> = {
  tool: '🔧',
  llm: '💬',
  human: '👤',
}

const kindColors: Record<PlanNode['kind'], string> = {
  tool: 'border-emerald-500/40 bg-emerald-500/5',
  llm: 'border-blue-500/40 bg-blue-500/5',
  human: 'border-amber-500/40 bg-amber-500/5',
}

export const PlanView = memo(function PlanView({ plan }: Props) {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">📋 执行计划</h4>
        <span className="text-xs text-muted-foreground">
          {plan.nodes.length} 个节点 · RAG {plan.rag_hits_count} 命中
        </span>
      </div>
      {plan.rationale && (
        <p className="text-xs text-muted-foreground italic">{plan.rationale}</p>
      )}
      <div className="space-y-2">
        {plan.nodes.map((node, idx) => (
          <div key={node.id} className="flex items-start gap-2">
            <span className="text-xs text-muted-foreground mt-1 w-6 text-right">{idx + 1}.</span>
            <div className={cn(
              'flex-1 rounded-md border px-3 py-2 text-xs',
              kindColors[node.kind],
            )}>
              <div className="flex items-center gap-2">
                <span>{kindIcons[node.kind]}</span>
                <span className="font-medium">{node.title}</span>
                <Badge variant="outline" className="text-[10px]">{node.kind}</Badge>
                {node.binding && (
                  <span className="font-mono text-[10px] text-muted-foreground truncate">
                    {node.binding.length > 40 ? node.binding.slice(0, 40) + '…' : node.binding}
                  </span>
                )}
              </div>
              {node.depends_on && node.depends_on.length > 0 && (
                <div className="mt-1 text-[10px] text-muted-foreground">
                  depends on: {node.depends_on.join(', ')}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
})
