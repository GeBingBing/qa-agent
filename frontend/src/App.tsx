// App — 顶层布局

import { ChatPanel } from './components/ChatPanel'
import { Sidebar } from './components/Sidebar'

export default function App() {
  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <main className="flex-1">
        <ChatPanel />
      </main>
    </div>
  )
}
