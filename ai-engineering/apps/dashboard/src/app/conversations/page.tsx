"use client"

import { useEffect, useState, useRef } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { Send, Plus, Loader2, ArrowRight, Bot, User } from "lucide-react"
import { cn } from "@/lib/utils"

const API = "http://127.0.0.1:8001"

interface CEOMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: string
  action: string | null
}

interface CEOConversation {
  id: string
  client_name: string
  project_name: string
  messages: CEOMessage[]
  status: string
  workflow_run_id: string | null
  created_at: string
  updated_at: string
}

interface ConvSummary {
  id: string
  client_name: string
  project_name: string
  status: string
  message_count: number
  created_at: string
  updated_at: string
  workflow_run_id: string | null
}

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<ConvSummary[]>([])
  const [activeConv, setActiveConv] = useState<CEOConversation | null>(null)
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [creating, setCreating] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    loadConversations()
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [activeConv?.messages])

  const loadConversations = async () => {
    try {
      const res = await fetch(`${API}/api/ce/conversations`)
      const data = await res.json()
      setConversations(data.conversations || [])
    } catch (e) {
      console.error("Failed to load conversations:", e)
    }
  }

  const loadConversation = async (id: string) => {
    try {
      const res = await fetch(`${API}/api/ce/conversations/${id}`)
      const data = await res.json()
      setActiveConv(data)
    } catch (e) {
      console.error("Failed to load conversation:", e)
    }
  }

  const createConversation = async () => {
    setCreating(true)
    try {
      const res = await fetch(`${API}/api/ce/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_name: "Client", project_name: "New Project" }),
      })
      const data = await res.json()
      if (data.id) {
        await loadConversation(data.id)
        await loadConversations()
      }
    } catch (e) {
      console.error("Failed to create conversation:", e)
    }
    setCreating(false)
  }

  const sendMessage = async () => {
    if (!activeConv || !input.trim() || sending) return
    const message = input.trim()
    setInput("")
    setSending(true)

    // Optimistic add
    const optimisticMsg: CEOMessage = {
      id: "temp",
      role: "user",
      content: message,
      timestamp: new Date().toISOString(),
      action: null,
    }
    setActiveConv((prev) =>
      prev ? { ...prev, messages: [...prev.messages, optimisticMsg] } : prev
    )

    try {
      const res = await fetch(`${API}/api/ce/conversations/${activeConv.id}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      })
      const data = await res.json()
      if (data.response) {
        // Reload full conversation to get proper messages
        await loadConversation(activeConv.id)
        await loadConversations()
      }
    } catch (e) {
      console.error("Failed to send message:", e)
    }
    setSending(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <DashboardLayout>
      <div className="flex h-[calc(100vh-4rem)] gap-4">
        {/* Sidebar - Conversation List */}
        <div className="w-72 border border-border rounded-lg flex flex-col bg-card">
          <div className="p-3 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-semibold">Conversations</h2>
            <button
              onClick={createConversation}
              disabled={creating}
              className="p-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {conversations.length === 0 ? (
              <div className="p-4 text-center text-muted-foreground text-sm">
                No conversations yet
              </div>
            ) : (
              conversations.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => loadConversation(conv.id)}
                  className={cn(
                    "w-full text-left p-3 border-b border-border hover:bg-accent/50 transition-colors",
                    activeConv?.id === conv.id && "bg-accent"
                  )}
                >
                  <div className="text-sm font-medium truncate">
                    {conv.project_name || "New Project"}
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={cn(
                      "text-xs px-1.5 py-0.5 rounded-full",
                      conv.status === "active" ? "bg-green-500/10 text-green-500" :
                      conv.status === "forwarded" ? "bg-blue-500/10 text-blue-500" :
                      "bg-muted text-muted-foreground"
                    )}>
                      {conv.status}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {conv.message_count} msgs
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Main Chat Area */}
        <div className="flex-1 flex flex-col border border-border rounded-lg bg-card">
          {!activeConv ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center space-y-4">
                <Bot className="h-16 w-16 mx-auto text-muted-foreground/50" />
                <div>
                  <h3 className="text-lg font-semibold">Layer 1: CEO</h3>
                  <p className="text-muted-foreground text-sm mt-1">
                    Start a new conversation to discuss your project with our CEO.
                  </p>
                </div>
                <button
                  onClick={createConversation}
                  disabled={creating}
                  className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 text-sm"
                >
                  {creating ? (
                    <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Starting...</span>
                  ) : (
                    <span className="flex items-center gap-2"><Plus className="h-4 w-4" /> New Conversation</span>
                  )}
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Header */}
              <div className="p-3 border-b border-border flex items-center gap-3">
                <Bot className="h-5 w-5 text-primary" />
                <div>
                  <div className="text-sm font-semibold">CEO - Layer 1</div>
                  <div className="text-xs text-muted-foreground">
                    {activeConv.status === "forwarded" ? (
                      <span className="flex items-center gap-1">
                        <ArrowRight className="h-3 w-3" /> Forwarded to Engineering (Workflow: {activeConv.workflow_run_id?.slice(0, 8)}...)
                      </span>
                    ) : (
                      "Discussing your project"
                    )}
                  </div>
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {activeConv.messages.length === 0 && (
                  <div className="text-center text-muted-foreground text-sm py-8">
                    Describe your project and the CEO will help plan it out.
                  </div>
                )}
                {activeConv.messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn(
                      "flex gap-3",
                      msg.role === "user" ? "justify-end" : "justify-start"
                    )}
                  >
                    {msg.role === "assistant" && (
                      <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                        <Bot className="h-4 w-4 text-primary" />
                      </div>
                    )}
                    <div
                      className={cn(
                        "max-w-[70%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap",
                        msg.role === "user"
                          ? "bg-primary text-primary-foreground"
                          : "bg-accent text-accent-foreground"
                      )}
                    >
                      {msg.content}
                      {msg.action === "forwarded_to_layer2" && (
                        <div className="mt-2 pt-2 border-t border-current/20">
                          <a
                            href="/workflow"
                            className="inline-flex items-center gap-1 text-xs underline opacity-80 hover:opacity-100"
                          >
                            View in Workflow Dashboard <ArrowRight className="h-3 w-3" />
                          </a>
                        </div>
                      )}
                    </div>
                    {msg.role === "user" && (
                      <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0">
                        <User className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                ))}
                {sending && (
                  <div className="flex gap-3 justify-start">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Bot className="h-4 w-4 text-primary" />
                    </div>
                    <div className="bg-accent rounded-lg px-4 py-2 text-sm">
                      <Loader2 className="h-4 w-4 animate-spin" />
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              {activeConv.status !== "forwarded" && (
                <div className="p-3 border-t border-border">
                  <div className="flex gap-2">
                    <textarea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Describe your project..."
                      rows={1}
                      className="flex-1 resize-none rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                    <button
                      onClick={sendMessage}
                      disabled={!input.trim() || sending}
                      className="px-3 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                    >
                      <Send className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1 px-1">
                    Say &quot;start building&quot; or &quot;let&apos;s go&quot; to hand off to the engineering team
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </DashboardLayout>
  )
}
