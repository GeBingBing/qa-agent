export type Domain = 'hr' | 'finance' | 'it' | 'legal' | 'general'
export type RiskLevel = 'low' | 'medium' | 'high'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: number
  // 流式中间状态
  intake?: IntakeEvent
  plan?: PlanEvent
  steps?: StepEvent[]
  risk?: RiskEvent
  reflection?: ReflectionEvent
  domain?: Domain
  costUsd?: number
  thinking?: string          // <think>...</think> 内累积的内容
  thinkingActive?: boolean   // 是否仍在思考中（最后一个 thinking_delta 之后到 answer_delta 开始前）
}

export interface IntakeEvent {
  domain: Domain
  intent: string
  confidence: number
  reasoning: string
  needs_tools: boolean
}

export interface PlanNode {
  id: string
  kind: 'llm' | 'tool' | 'human'
  title: string
  description?: string
  binding?: string
  depends_on?: string[]
}

export interface PlanEvent {
  rationale: string
  nodes: PlanNode[]
  rag_hits_count: number
  selected_skills: any[]
  blocked_skills: any[]
}

export interface StepEvent {
  id: string
  kind: 'llm' | 'tool' | 'human'
  title: string
  status?: string
  observation?: any
  content?: string
  error?: string
}

export interface RiskEvent {
  risk_level: RiskLevel
  auto_proceed: boolean
  reasons: string[]
  required_approver: string
}

export interface ReflectionEvent {
  rounds: number
  evaluations: Array<{ passed: boolean; score: number; issues: string[]; suggestions: string[] }>
}

export interface StreamEvent {
  event:
    | 'start'
    | 'intake'
    | 'plan'
    | 'step_start'
    | 'step_result'
    | 'risk'
    | 'thinking_delta'
    | 'answer_delta'
    | 'final'
    | 'error'
  data: any
  timestamp?: number
}

export interface HealthResponse {
  status: string
  active_provider: string
  available_providers: string[]
  total_tools: number
  skills_loaded: number
}
