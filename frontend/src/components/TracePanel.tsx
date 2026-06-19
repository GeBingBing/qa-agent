// TracePanel — 实时显示执行进度 (intake → plan → steps → risk → final)

import { memo } from 'react'
import type { ChatMessage } from '@/types/chat'
import { DomainBadge, RiskBadge } from './DomainBadge'
import { PlanView } from './PlanView'
import { Badge } from './ui/badge'
import { Loader2 } from 'lucide-react'

interface Props {
  message: ChatMessage
}

export const TracePanel = memo(function TracePanel({ message }: Props) {
  return (
    <div className="space-y-2 text-xs">
      {/* Intake */}
      {message.intake && (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-secondary/30 px-3 py-2">
          <span className="text-muted-foreground">路由 →</span>
          <DomainBadge domain={message.intake.domain} />
          <span className="text-muted-foreground">·</span>
          <span>意图: <code className="text-[11px]">{message.intake.intent}</code></span>
          <span className="text-muted-foreground">·</span>
          <span>置信度: {(message.intake.confidence * 100).toFixed(0)}%</span>
          {message.intake.needs_tools && (
            <Badge variant="outline" className="text-[10px]">需调工具</Badge>
          )}
        </div>
      )}

      {/* Plan */}
      {message.plan && <PlanView plan={message.plan} />}

      {/* Steps */}
      {message.steps && message.steps.length > 0 && (
        <div className="space-y-1 rounded-md border border-border bg-card p-3">
          <h5 className="text-[11px] font-semibold text-muted-foreground">⚙️ 执行步骤</h5>
          {message.steps.map((step, i) => (
            <div key={step.id ?? i} className="space-y-1 rounded-sm bg-secondary/20 px-2 py-1 text-[11px]">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">#{i + 1}</span>
                <span>{step.kind === 'tool' ? '🔧' : step.kind === 'llm' ? '💬' : '👤'}</span>
                <span className="font-mono">{step.id}</span>
                <span className="text-muted-foreground">· {step.title}</span>
                {step.status === 'running' ? (
                  <Loader2 className="h-3 w-3 animate-spin text-primary" />
                ) : step.status ? (
                  <Badge
                    variant="outline"
                    className={`text-[10px] ${step.status === 'error' ? 'text-rose-400' : ''}`}
                  >
                    {step.status}
                  </Badge>
                ) : null}
              </div>
              {(step.observation ?? step.content ?? step.error) && (
                <div className="line-clamp-2 pl-12 text-[10px] text-muted-foreground">
                  {typeof (step.observation ?? step.content ?? step.error) === 'string'
                    ? (step.observation ?? step.content ?? step.error)
                    : JSON.stringify(step.observation ?? step.content ?? step.error)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Risk */}
      {message.risk && (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-secondary/30 px-3 py-2">
          <span className="text-muted-foreground">风险评估 →</span>
          <RiskBadge level={message.risk.risk_level} />
          <span className="text-muted-foreground">·</span>
          <span>审批人: <code className="text-[11px]">{message.risk.required_approver}</code></span>
          {message.risk.reasons.length > 0 && (
            <span className="text-[10px] text-muted-foreground truncate">
              {message.risk.reasons[0]}
            </span>
          )}
        </div>
      )}

      {/* Reflection */}
      {message.reflection && message.reflection.rounds > 0 && (
        <div className="flex items-center gap-2 rounded-md bg-secondary/30 px-3 py-2">
          <span className="text-muted-foreground">反思 →</span>
          <span>经过 {message.reflection.rounds} 轮迭代</span>
          {message.reflection.evaluations.length > 0 && (
            <span className="text-[10px] text-muted-foreground">
              最终评分 {(message.reflection.evaluations[message.reflection.evaluations.length - 1].score * 100).toFixed(0)}%
            </span>
          )}
        </div>
      )}
    </div>
  )
})
