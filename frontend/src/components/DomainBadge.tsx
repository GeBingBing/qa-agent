// Domain 颜色映射 Badge

import { Badge } from './ui/badge'
import type { Domain } from '@/types/chat'

const domainColors: Record<Domain, string> = {
  hr:      'bg-blue-600/20 text-blue-400 border border-blue-600/30',
  finance: 'bg-emerald-600/20 text-emerald-400 border border-emerald-600/30',
  it:      'bg-purple-600/20 text-purple-400 border border-purple-600/30',
  legal:   'bg-rose-600/20 text-rose-400 border border-rose-600/30',
  general: 'bg-slate-600/20 text-slate-400 border border-slate-600/30',
}

const domainLabels: Record<Domain, string> = {
  hr: '人事 HR',
  finance: '财务 Finance',
  it: 'IT',
  legal: '法务 Legal',
  general: '通用',
}

export function DomainBadge({ domain }: { domain: Domain }) {
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${domainColors[domain]}`}>
      {domainLabels[domain]}
    </span>
  )
}

export function RiskBadge({ level }: { level: 'low' | 'medium' | 'high' }) {
  if (level === 'low') return <Badge variant="success">低风险</Badge>
  if (level === 'medium') return <Badge variant="warning">中风险</Badge>
  return <Badge variant="destructive">高风险</Badge>
}
