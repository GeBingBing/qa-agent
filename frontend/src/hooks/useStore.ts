// Zustand 全局状态 — 对话历史 / 当前流式状态

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { ChatMessage, IntakeEvent, PlanEvent, RiskEvent, ReflectionEvent, StepEvent, Domain } from '@/types/chat'

function genId(prefix: 'u' | 'a'): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  // 老浏览器降级（生产环境基本不会进这里）
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

interface ChatState {
  messages: ChatMessage[]
  isStreaming: boolean
  streamingId: string | null

  addUserMessage: (content: string) => string
  startAssistantMessage: () => string
  appendAssistantContent: (id: string, delta: string) => void
  appendAssistantThinking: (id: string, delta: string) => void
  finalizeAssistantThinking: (id: string) => void
  setAssistantIntake: (id: string, intake: IntakeEvent) => void
  setAssistantPlan: (id: string, plan: PlanEvent) => void
  addAssistantStep: (id: string, step: StepEvent) => void
  updateAssistantStep: (id: string, stepId: string, patch: Partial<StepEvent>) => void
  setAssistantSteps: (id: string, steps: StepEvent[]) => void
  setAssistantRisk: (id: string, risk: RiskEvent) => void
  setAssistantReflection: (id: string, reflection: ReflectionEvent) => void
  setAssistantDomain: (id: string, domain: Domain) => void
  finishStreaming: (id: string) => void
  reset: () => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      messages: [],
      isStreaming: false,
      streamingId: null,

      addUserMessage: (content) => {
        const id = genId('u')
        set((s) => ({
          messages: [...s.messages, {
            id, role: 'user', content, createdAt: Date.now(),
          }],
        }))
        return id
      },

      startAssistantMessage: () => {
        const id = genId('a')
        set((s) => ({
          isStreaming: true,
          streamingId: id,
          messages: [...s.messages, {
            id, role: 'assistant', content: '', createdAt: Date.now(),
          }],
        }))
        return id
      },

      appendAssistantContent: (id, delta) => {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, content: m.content + delta, thinkingActive: false } : m
          ),
        }))
      },

      appendAssistantThinking: (id, delta) => {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id
              ? { ...m, thinking: (m.thinking ?? '') + delta, thinkingActive: true }
              : m
          ),
        }))
      },

      finalizeAssistantThinking: (id) => {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, thinkingActive: false } : m
          ),
        }))
      },

      setAssistantIntake: (id, intake) => {
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, intake } : m)),
        }))
      },

      setAssistantPlan: (id, plan) => {
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, plan } : m)),
        }))
      },

      addAssistantStep: (id, step) => {
        set((s) => ({
          messages: s.messages.map((m) => {
            if (m.id !== id) return m
            const existing = m.steps ?? []
            if (existing.some((x) => x.id === step.id)) return m
            return { ...m, steps: [...existing, step] }
          }),
        }))
      },

      updateAssistantStep: (id, stepId, patch) => {
        set((s) => ({
          messages: s.messages.map((m) => {
            if (m.id !== id) return m
            const steps = (m.steps ?? []).map((step) =>
              step.id === stepId ? { ...step, ...patch } : step
            )
            if (!steps.some((step) => step.id === stepId)) {
              steps.push({
                id: stepId,
                kind: (patch.kind as StepEvent['kind']) ?? 'llm',
                title: patch.title ?? stepId,
                ...patch,
              })
            }
            return { ...m, steps }
          }),
        }))
      },

      setAssistantSteps: (id, steps) => {
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, steps } : m)),
        }))
      },

      setAssistantRisk: (id, risk) => {
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, risk } : m)),
        }))
      },

      setAssistantReflection: (id, reflection) => {
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, reflection } : m)),
        }))
      },

      setAssistantDomain: (id, domain) => {
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, domain } : m)),
        }))
      },

      finishStreaming: (id) => {
        set((s) => ({
          isStreaming: false,
          streamingId: s.streamingId === id ? null : s.streamingId,
        }))
      },

      reset: () => {
        set({ messages: [], isStreaming: false, streamingId: null })
      },
    }),
    {
      name: 'kb-qa-agent-chat',
      version: 1,
      storage: createJSONStorage(() => localStorage),
      // 只持久化对话本身；瞬时状态（流式中）不写盘
      partialize: (state) => ({ messages: state.messages }) as Partial<ChatState>,
      // 重新加载时强制把 streaming 标志清掉，避免上次崩溃留下的脏状态
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.isStreaming = false
          state.streamingId = null
        }
      },
    },
  ),
)
