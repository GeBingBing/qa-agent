// SSE 流 hook — 把后端事件映射到 Zustand store

import { useCallback, useRef } from 'react'
import { streamChat } from '@/lib/api'
import { toast } from '@/components/Toast'
import { useChatStore } from './useStore'

export function useChatStream() {
  const {
    addUserMessage,
    startAssistantMessage,
    appendAssistantContent,
    appendAssistantThinking,
    finalizeAssistantThinking,
    setAssistantIntake,
    setAssistantPlan,
    setAssistantSources,
    addAssistantStep,
    updateAssistantStep,
    setAssistantRisk,
    setAssistantReflection,
    setAssistantDomain,
    finishStreaming,
  } = useChatStore()

  const abortRef = useRef<AbortController | null>(null)

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  const send = useCallback(async (query: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    addUserMessage(query)
    const aid = startAssistantMessage()

    try {
      for await (const evt of streamChat({ query }, { signal: controller.signal })) {
        switch (evt.event) {
          case 'intake':
            setAssistantIntake(aid, evt.data)
            setAssistantDomain(aid, evt.data.domain)
            break
          case 'plan':
            setAssistantPlan(aid, evt.data)
            break
          case 'sources':
            if (Array.isArray(evt.data)) setAssistantSources(aid, evt.data)
            break
          case 'step_start':
            addAssistantStep(aid, {
              id: evt.data.id,
              kind: evt.data.kind,
              title: evt.data.title,
              status: 'running',
            })
            break
          case 'step_result':
            updateAssistantStep(aid, evt.data.id, {
              kind: evt.data.kind,
              status: evt.data.status,
              observation: evt.data.observation,
              content: evt.data.content,
              error: evt.data.error,
            })
            break
          case 'risk':
            setAssistantRisk(aid, evt.data)
            break
          case 'thinking_delta':
            if (evt.data?.delta) appendAssistantThinking(aid, evt.data.delta)
            break
          case 'answer_delta':
            if (evt.data?.delta) appendAssistantContent(aid, evt.data.delta)
            break
          case 'final':
            finalizeAssistantThinking(aid)
            if (evt.data?.final_answer) {
              useChatStore.setState((s) => ({
                messages: s.messages.map((m) =>
                  m.id === aid ? { ...m, content: evt.data.final_answer } : m
                ),
              }))
            }
            setAssistantReflection(aid, {
              rounds: evt.data?.reflection_rounds ?? 0,
              evaluations: evt.data?.evaluations ?? [],
            })
            break
          case 'error':
            appendAssistantContent(aid, `\n\n[错误] ${JSON.stringify(evt.data)}`)
            break
        }
      }
    } catch (err: any) {
      if (err?.name === 'AbortError' || controller.signal.aborted) {
        appendAssistantContent(aid, '\n\n_（已中断）_')
      } else {
        const msg = err?.message ?? String(err)
        toast.error(`连接失败：${msg}`)
        appendAssistantContent(aid, `\n\n[连接失败] ${msg}`)
      }
    } finally {
      finalizeAssistantThinking(aid)
      finishStreaming(aid)
      if (abortRef.current === controller) abortRef.current = null
    }
  }, [])

  return { send, cancel }
}
