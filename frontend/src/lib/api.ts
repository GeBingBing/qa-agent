// SSE 客户端 — 解析 /v1/chat 流式响应

import type { StreamEvent } from '@/types/chat'
import { apiUrl } from './config'

export async function* streamChat(
  request: {
    query: string
    conversation_history?: any[]
    provider?: string
    model?: string
    enable_reflection?: boolean
    enable_rag?: boolean
    enable_skills?: boolean
  },
  options?: { signal?: AbortSignal },
): AsyncGenerator<StreamEvent> {
  const resp = await fetch(apiUrl('/v1/chat'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_history: [],
      enable_reflection: true,
      enable_rag: true,
      enable_skills: true,
      ...request,
    }),
    signal: options?.signal,
  })

  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${await resp.text()}`)
  }
  if (!resp.body) {
    throw new Error('No response body')
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  // signal 触发时取消底层 reader，让循环干净退出
  const onAbort = () => {
    reader.cancel().catch(() => undefined)
  }
  options?.signal?.addEventListener('abort', onAbort)

  try {
    while (true) {
      let chunk: ReadableStreamReadResult<Uint8Array>
      try {
        chunk = await reader.read()
      } catch (err) {
        if (options?.signal?.aborted) return
        throw err
      }
      if (chunk.done) break
      buf += decoder.decode(chunk.value, { stream: true })
      buf = buf.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

      // SSE 格式：event: <type>\ndata: <json>\n\n
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const event = parseSSEBlock(block)
        if (event) yield event
      }
    }
  } finally {
    options?.signal?.removeEventListener('abort', onAbort)
  }
}

function parseSSEBlock(block: string): StreamEvent | null {
  let eventName = 'message'
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
  }
  if (dataLines.length === 0) return null
  try {
    const data = JSON.parse(dataLines.join('\n'))
    return { event: eventName as StreamEvent['event'], data, timestamp: Date.now() }
  } catch {
    return null
  }
}
