// SkillList — 列出命中 / 阻断的 Skills

import { memo } from 'react'
import type { PlanEvent } from '@/types/chat'
import { Badge } from './ui/badge'

interface Props {
  plan: PlanEvent
}

export const SkillList = memo(function SkillList({ plan }: Props) {
  const selected = plan.selected_skills || []
  const blocked = plan.blocked_skills || []
  if (selected.length === 0 && blocked.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      {selected.map((s: any, i: number) => (
        <Badge key={i} variant="success" className="text-[10px]">
          ✨ {s.skill_id ?? s.skillId ?? s.name ?? JSON.stringify(s).slice(0, 30)}
        </Badge>
      ))}
      {blocked.map((b: any, i: number) => (
        <Badge key={`b-${i}`} variant="outline" className="text-[10px] opacity-60">
          🚫 {b[0]?.skill_id ?? b.skill_id ?? '?'}
        </Badge>
      ))}
    </div>
  )
})
