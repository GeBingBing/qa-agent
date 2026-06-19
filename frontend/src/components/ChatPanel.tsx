// ChatPanel — 主对话区

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore } from '@/hooks/useStore'
import { useChatStream } from '@/hooks/useChatStream'
import { TracePanel } from './TracePanel'
import { ThinkingPanel } from './ThinkingPanel'
import { SkillList } from './SkillList'
import { DomainBadge } from './DomainBadge'
import { Button } from './ui/button'
import { CopyButton, ActionButton } from './MessageActions'
import { Send, RotateCcw, Square } from 'lucide-react'

const QUICK_PROMPTS = [
  '我下个月想休 5 天年假，需要什么流程？',
  'AWS 这份合同是否符合 GDPR？',
  '我的 IT 工单 T001 处理到哪一步了？',
  '差旅报销的标准是多少？',
]

export function ChatPanel() {
  const { messages, isStreaming } = useChatStore()
  const { send, cancel } = useChatStream()
  const reset = useChatStore((s) => s.reset)
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function submitQuery(query: string) {
    const q = query.trim()
    if (!q || isStreaming) return
    setInput('')
    await send(q)
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    await submitQuery(input)
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter 发送 / Shift+Enter 换行
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void submitQuery(input)
    }
  }

  function handleClear() {
    if (messages.length === 0) return
    const ok = window.confirm('确定要清空当前对话吗？该操作不可恢复。')
    if (ok) reset()
  }

  /** 找到上一条用户消息，作为重发或编辑的来源 */
  function findLastUserBefore(messageId: string): string | null {
    const idx = messages.findIndex((m) => m.id === messageId)
    if (idx === -1) return null
    for (let i = idx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') return messages[i].content
    }
    return null
  }

  function regenerate(assistantMessageId: string) {
    const q = findLastUserBefore(assistantMessageId)
    if (!q) return
    void submitQuery(q)
  }

  function loadIntoInput(text: string) {
    setInput(text)
    inputRef.current?.focus()
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border bg-card/50 px-6 py-3">
        <div>
          <h2 className="text-lg font-semibold">💬 企业知识库问答</h2>
          <p className="text-xs text-muted-foreground">
            7 Provider 切换 · RAG + MCP + Skills + 沙盒 + 反思 · SSE 流式
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClear}
          aria-label="清空对话"
          disabled={messages.length === 0}
        >
          <RotateCcw className="h-4 w-4 mr-1" />
          清空对话
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6" aria-live="polite">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            <div className="text-center space-y-3">
              <p className="text-base">👋 你好！</p>
              <p>试试问：</p>
              <div className="space-y-1 text-left text-xs">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={isStreaming}
                    onClick={() => submitQuery(prompt)}
                    className="block w-full rounded-md bg-secondary/50 px-3 py-2 text-left transition hover:bg-secondary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    「{prompt}」
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`group max-w-3xl space-y-2 rounded-lg px-4 py-3 ${
                m.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card border border-border'
              }`}
            >
              {m.role === 'assistant' && m.domain && (
                <div className="flex items-center gap-2 text-xs">
                  <DomainBadge domain={m.domain} />
                </div>
              )}

              {m.role === 'assistant' && <TracePanel message={m} />}

              {m.role === 'assistant' && (m.thinking || m.thinkingActive) && (
                <ThinkingPanel
                  thinking={m.thinking ?? ''}
                  active={!!m.thinkingActive}
                />
              )}

              <div className="prose prose-sm prose-invert max-w-none leading-relaxed">
                {m.role === 'assistant' ? (
                  m.content ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  ) : (
                    <span className="whitespace-pre-wrap text-muted-foreground">
                      {m.thinkingActive ? '正在思考…' : isStreaming ? '...' : ''}
                    </span>
                  )
                ) : (
                  <span className="whitespace-pre-wrap">{m.content}</span>
                )}
              </div>

              {m.role === 'assistant' && m.plan && <SkillList plan={m.plan} />}

              {/* 操作条：助手 → 复制 / 重新生成；用户 → 复制 / 编辑 */}
              {m.content && (
                <div
                  className={`flex items-center gap-1 pt-1 text-[11px] ${
                    m.role === 'user' ? 'justify-end' : 'justify-start'
                  } opacity-0 transition group-hover:opacity-100 focus-within:opacity-100`}
                >
                  <CopyButton text={m.content} />
                  {m.role === 'assistant' ? (
                    <ActionButton
                      label="重新生成"
                      icon="retry"
                      onClick={() => regenerate(m.id)}
                      disabled={isStreaming}
                    />
                  ) : (
                    <ActionButton
                      label="编辑"
                      icon="edit"
                      onClick={() => loadIntoInput(m.content)}
                      disabled={isStreaming}
                    />
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form onSubmit={onSubmit} className="border-t border-border bg-card/50 px-6 py-3">
        <div className="flex items-end gap-2">
          <label htmlFor="chat-input" className="sr-only">
            输入问题
          </label>
          <textarea
            id="chat-input"
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="问点什么... (Shift+Enter 换行，Enter 发送)"
            disabled={isStreaming}
            rows={1}
            className="flex-1 max-h-40 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
          <Button
            type={isStreaming ? 'button' : 'submit'}
            variant={isStreaming ? 'destructive' : 'default'}
            disabled={!isStreaming && !input.trim()}
            onClick={isStreaming ? () => cancel() : undefined}
            aria-label={isStreaming ? '停止生成' : '发送'}
          >
            {isStreaming ? <Square className="h-4 w-4" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </form>
    </div>
  )
}
