// Sidebar — 元信息面板 (健康状态 + 工具数 + Skills 数 + Provider)

import { useQuery } from '@tanstack/react-query'
import type { HealthResponse } from '@/types/chat'
import { apiUrl } from '@/lib/config'
import { Badge } from './ui/badge'

export function Sidebar() {
  const { data: health, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: async (): Promise<HealthResponse> => {
      const r = await fetch(apiUrl('/health'))
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json()
    },
  })

  return (
    <aside className="w-72 flex-shrink-0 border-r border-border bg-card/30 p-4 space-y-4 overflow-y-auto">
      <div>
        <h3 className="text-sm font-semibold mb-2">🩺 服务状态</h3>
        {isLoading ? (
          <div className="text-xs text-muted-foreground">加载中…</div>
        ) : health ? (
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">状态</span>
              <Badge variant="success">{health.status}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Active Provider</span>
              <code className="text-[10px]">{health.active_provider}</code>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">工具数</span>
              <span>{health.total_tools}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Skills</span>
              <span>{health.skills_loaded}</span>
            </div>
            <div className="pt-2 border-t border-border">
              <div className="text-muted-foreground mb-1">Available Providers</div>
              <div className="flex flex-wrap gap-1">
                {health.available_providers.length === 0 ? (
                  <span className="text-[10px] text-rose-400">⚠️ 无可用 Provider（检查 .env）</span>
                ) : (
                  health.available_providers.map((p) => (
                    <Badge key={p} variant="outline" className="text-[10px]">{p}</Badge>
                  ))
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-xs text-rose-400">⚠️ 无法连接后端（http://localhost:8000）</div>
        )}
      </div>

      <div className="pt-4 border-t border-border">
        <h3 className="text-sm font-semibold mb-2">🧠 核心能力</h3>
        <div className="space-y-1 text-[11px] text-muted-foreground">
          <div>✅ 7 Provider 适配</div>
          <div>✅ 单次请求 + Schema 输出</div>
          <div>✅ TriggerFlow 流程编排</div>
          <div>✅ ReAct Loop（含 Grace Call）</div>
          <div>✅ 意图路由 / DAG 规划 / 反思</div>
          <div>✅ Tool Registry（12 工具）</div>
          <div>✅ MCP 集成（外部 + 自建）</div>
          <div>✅ Bash 沙盒</div>
          <div>✅ SSE 流式 Agent</div>
          <div>✅ Skills 加载 / 选择 / 信任门</div>
          <div>✅ Trace + Cost 可观测性</div>
        </div>
      </div>
    </aside>
  )
}
