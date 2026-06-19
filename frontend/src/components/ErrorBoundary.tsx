// ErrorBoundary — 顶层 React 错误兜底，避免白屏

import { Component, type ReactNode } from 'react'

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // 留个 console，便于在 DevTools 里看堆栈
    console.error('[ErrorBoundary]', error, info)
  }

  reset = () => this.setState({ error: null })

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="flex h-full min-h-[60vh] items-center justify-center p-8">
        <div className="max-w-lg space-y-3 rounded-lg border border-rose-500/40 bg-rose-500/5 p-6 text-sm">
          <div className="text-base font-semibold text-rose-300">⚠️ 出错了</div>
          <p className="text-muted-foreground">页面渲染出现异常，已被错误边界捕获。</p>
          <pre className="overflow-x-auto rounded-sm bg-secondary/60 p-3 text-xs">
            {this.state.error.message}
          </pre>
          <button
            type="button"
            onClick={this.reset}
            className="rounded-md bg-primary px-3 py-1 text-xs text-primary-foreground hover:bg-primary/90"
          >
            重试
          </button>
        </div>
      </div>
    )
  }
}
