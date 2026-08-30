"use client"

import { useEffect, useState, useRef } from "react"
import Link from "next/link"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  BookMarked,
  FileSearch,
  Sparkles,
  Loader2,
  Send,
  Plus,
  Bot,
  User,
  ArrowRight,
  Trash2,
  MessageSquare,
  ChevronLeft,
  Pencil,
  Check,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"

const API = "http://127.0.0.1:8001"

interface Repository { id: string; name: string; description: string; icon: string; accent: string; tags: string[]; categories: number; items: number; updated_at: string }
interface Stats { repositories: number; items: number; categories: number }
interface SearchResult { repo_id: string; repo_name: string; category: string; item: { id: string; title: string; summary: string; content: string; tags: string[]; rules: string[] }; score: number }
interface Briefing { task_type: string; matched_repositories: string[]; summary: string; items: { repo_id: string; repo_name: string; category: string; item: { id: string; title: string; summary: string; content: string; rules: string[] } }[] }
interface CEOMsg { id: string; role: "user" | "assistant"; content: string; timestamp: string; action: string | null; task_id?: string | null }
interface CEOConv { id: string; client_name: string; project_name: string; messages: CEOMsg[]; status: string; workflow_run_id: string | null; created_at: string; updated_at: string }
interface ConvSummary { id: string; project_name: string; status: string; message_count: number; created_at: string; workflow_run_id: string | null }

export default function Layer1Page() {
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [briefTask, setBriefTask] = useState("")
  const [briefing, setBriefing] = useState<Briefing | null>(null)
  const [briefingLoading, setBriefingLoading] = useState(false)
  const [showKB, setShowKB] = useState(false)

  const [conversations, setConversations] = useState<ConvSummary[]>([])
  const [activeConv, setActiveConv] = useState<CEOConv | null>(null)
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [creating, setCreating] = useState(false)
  const [chatError, setChatError] = useState("")
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => { fetchKB(); loadConversations() }, [])
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }) }, [activeConv?.messages])

  const fetchKB = () => {
    fetch(`${API}/api/kb/repositories`).then(r => r.json())
      .then(d => { setRepositories(d.repositories || []); setStats(d.stats || null) })
      .catch(() => {})
  }

  const loadConversations = async () => {
    try { const r = await fetch(`${API}/api/ce/conversations`); if (!r.ok) throw new Error(); const d = await r.json(); setConversations(d.conversations || []) } catch {}
  }

  const loadConversation = async (id: string) => {
    try { setChatError(""); const r = await fetch(`${API}/api/ce/conversations/${id}`); if (!r.ok) throw new Error(); const d = await r.json(); setActiveConv(d) } catch { setChatError("Failed to load") }
  }

  const createConversation = async () => {
    setCreating(true); setChatError("")
    try {
      const r = await fetch(`${API}/api/ce/conversations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ client_name: "Client", project_name: "New Project" }) })
      if (!r.ok) throw new Error()
      const d = await r.json()
      if (d.id) { await loadConversation(d.id); await loadConversations() }
    } catch { setChatError("Failed to create") }
    setCreating(false)
  }

  const deleteConversation = async (id: string) => {
    if (!confirm("Delete this conversation?")) return
    try {
      await fetch(`${API}/api/ce/conversations/${id}`, { method: "DELETE" })
      if (activeConv?.id === id) setActiveConv(null)
      await loadConversations()
    } catch {}
  }

  const startRename = (id: string, currentName: string) => {
    setRenamingId(id)
    setRenameValue(currentName || "")
  }

  const confirmRename = async () => {
    if (!renamingId || !renameValue.trim()) { setRenamingId(null); return }
    try {
      await fetch(`${API}/api/ce/conversations/${renamingId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_name: renameValue.trim() }),
      })
      if (activeConv?.id === renamingId) setActiveConv(p => p ? { ...p, project_name: renameValue.trim() } : p)
      await loadConversations()
    } catch {}
    setRenamingId(null)
  }

  const sendMessage = async () => {
    if (!activeConv || !input.trim() || sending) return
    const msg = input.trim(); const convId = activeConv.id
    setInput(""); setSending(true); setChatError("")
    setActiveConv(p => p ? { ...p, messages: [...p.messages, { id: "temp-" + Date.now(), role: "user", content: msg, timestamp: new Date().toISOString(), action: null }] } : p)
    try {
      const r = await fetch(`${API}/api/ce/conversations/${convId}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: msg }) })
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.error || `HTTP ${r.status}`) }
      await loadConversation(convId); await loadConversations()
    } catch (e) { setChatError(`Send failed: ${e instanceof Error ? e.message : "Unknown"}`); try { await loadConversation(convId) } catch {} }
    setSending(false)
  }

  const runSearch = () => {
    if (!searchQuery.trim()) return; setSearching(true)
    fetch(`${API}/api/kb/search?q=${encodeURIComponent(searchQuery)}`).then(r => r.json()).then(d => setSearchResults(d.results || [])).catch(() => setSearchResults([])).finally(() => setSearching(false))
  }

  const runBriefing = () => {
    if (!briefTask.trim()) return; setBriefingLoading(true)
    fetch(`${API}/api/kb/agent-briefing`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task: briefTask }) }).then(r => r.json()).then(setBriefing).catch(() => setBriefing(null)).finally(() => setBriefingLoading(false))
  }

  return (
    <DashboardLayout>
      <div className="h-[calc(100vh-4rem)] flex -m-6">
        {/* Conversations Sidebar */}
        <div className="w-64 border-r border-border bg-card flex flex-col shrink-0">
          <div className="p-3 border-b border-border">
            <button onClick={createConversation} disabled={creating}
              className="w-full flex items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2.5 text-sm font-medium hover:bg-accent disabled:opacity-50 transition-colors">
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              New Chat
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
            {conversations.length === 0 && (
              <div className="px-3 py-8 text-center">
                <MessageSquare className="h-8 w-8 mx-auto mb-2 text-muted-foreground/30" />
                <p className="text-xs text-muted-foreground">No conversations yet</p>
              </div>
            )}
            {conversations.map(c => (
              <div key={c.id}
                className={cn(
                  "group flex items-center gap-2 rounded-lg px-3 py-2.5 cursor-pointer transition-colors",
                  activeConv?.id === c.id ? "bg-accent" : "hover:bg-accent/50"
                )}
                onClick={() => { if (renamingId !== c.id) loadConversation(c.id) }}>
                <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  {renamingId === c.id ? (
                    <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                      <input value={renameValue} onChange={e => setRenameValue(e.target.value)}
                        onKeyDown={e => { if (e.key === "Enter") confirmRename(); if (e.key === "Escape") setRenamingId(null) }}
                        autoFocus
                        className="flex-1 text-sm bg-background border border-border rounded px-1.5 py-0.5 outline-none focus:ring-1 focus:ring-primary" />
                      <button onClick={confirmRename} className="p-0.5 rounded hover:bg-green-500/10 text-green-400"><Check className="h-3.5 w-3.5" /></button>
                      <button onClick={() => setRenamingId(null)} className="p-0.5 rounded hover:bg-accent text-muted-foreground"><X className="h-3.5 w-3.5" /></button>
                    </div>
                  ) : (
                    <p className="text-sm font-medium truncate">{c.project_name || "Chat"}</p>
                  )}
                  <p className="text-[10px] text-muted-foreground">{c.message_count} messages</p>
                </div>
                {renamingId !== c.id && (
                  <div className="opacity-0 group-hover:opacity-100 flex items-center transition-all" onClick={e => e.stopPropagation()}>
                    <button onClick={() => startRename(c.id, c.project_name)}
                      className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground">
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button onClick={() => deleteConversation(c.id)}
                      className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="p-2 border-t border-border">
            <button onClick={() => setShowKB(!showKB)}
              className={cn("w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors", showKB ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-accent")}>
              <BookMarked className="h-4 w-4" />
              Knowledge Base
            </button>
          </div>
        </div>

        {/* Main Area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Chat header */}
          <div className="h-12 border-b border-border flex items-center px-4 justify-between shrink-0">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-primary" />
              <span className="text-sm font-semibold">Layer 1 — CEO Chat</span>
              {activeConv && <span className="text-xs text-muted-foreground">/ {activeConv.project_name}</span>}
            </div>
            {activeConv && (
              <span className={cn("text-[10px] font-medium px-2 py-0.5 rounded-full",
                activeConv.status === "forwarded" ? "bg-green-500/10 text-green-400" : "bg-blue-500/10 text-blue-400")}>
                {activeConv.status}
              </span>
            )}
          </div>

          {/* Error */}
          {chatError && (
            <div className="px-4 py-2 bg-destructive/10 border-b border-destructive/30 flex items-center gap-2 text-xs text-destructive">
              {chatError}
              <button onClick={() => setChatError("")} className="ml-auto underline">dismiss</button>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto">
            {!activeConv ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center space-y-4 max-w-md">
                  <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto">
                    <Bot className="h-8 w-8 text-primary" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold">What are you building?</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                      Describe your product, idea or problem. The CEO will analyze it and prepare it for development.
                    </p>
                  </div>
                  <button onClick={createConversation} disabled={creating}
                    className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                    {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                    Start a conversation
                  </button>
                </div>
              </div>
            ) : (
              <div className="max-w-3xl mx-auto p-4 space-y-4">
                {activeConv.messages.map(msg => (
                  <div key={msg.id} className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}>
                    {msg.role === "assistant" && (
                      <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                        <Bot className="h-4 w-4 text-primary" />
                      </div>
                    )}
                    <div className={cn("max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                      msg.role === "user" ? "bg-primary text-primary-foreground rounded-br-md" : "bg-accent text-accent-foreground rounded-bl-md")}>
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                      {msg.action === "forwarded_to_layer2" && (
                        <div className="mt-3 pt-2 border-t border-current/20">
                          <Link href="/workflow" className="inline-flex items-center gap-1 text-xs underline opacity-80 hover:opacity-100">
                            View in Workflow <ArrowRight className="h-3 w-3" />
                          </Link>
                        </div>
                      )}
                      {msg.action === "sent_to_dev_team" && (
                        <div className="mt-3 pt-2 border-t border-current/20">
                          <Link href={msg.task_id ? `/monitor?task=${msg.task_id}` : "/monitor"} className="inline-flex items-center gap-1 text-xs underline opacity-80 hover:opacity-100">
                            View in Monitor <ArrowRight className="h-3 w-3" />
                          </Link>
                        </div>
                      )}
                    </div>
                    {msg.role === "user" && (
                      <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5">
                        <User className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                ))}
                {sending && (
                  <div className="flex gap-3">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                      <Bot className="h-4 w-4 text-primary" />
                    </div>
                    <div className="bg-accent rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      <span className="text-sm text-muted-foreground">Thinking...</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-border p-4 shrink-0">
            <div className="max-w-3xl mx-auto">
              <div className="flex gap-2 items-end">
                <textarea value={input} onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
                  placeholder={activeConv?.status === "forwarded" ? "Continue the conversation..." : "Describe your project..."} rows={1} disabled={sending}
                  className="flex-1 resize-none rounded-xl border border-border bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 min-h-[48px]" />
                <button onClick={sendMessage} disabled={!input.trim() || sending}
                  className="p-3 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors">
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
              </div>
              <p className="text-[10px] text-muted-foreground mt-2 text-center">
                {activeConv?.status === "forwarded"
                  ? "Project has been sent. You can still ask questions or start a new one."
                  : "Say \"start building\" to hand off to layers, or \"send to dev team\" for quick fixes"}
              </p>
            </div>
          </div>
        </div>

        {/* Knowledge Base Panel (slide-in) */}
        {showKB && (
          <div className="w-80 border-l border-border bg-card flex flex-col shrink-0">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BookMarked className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">Knowledge Base</span>
              </div>
              <button onClick={() => setShowKB(false)} className="p-1 rounded hover:bg-accent text-muted-foreground">
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-4">
              <div className="grid grid-cols-3 gap-2">
                <div className="rounded-lg border border-border bg-background p-2 text-center">
                  <p className="text-lg font-bold">{stats?.repositories || 0}</p>
                  <p className="text-[10px] text-muted-foreground">Repos</p>
                </div>
                <div className="rounded-lg border border-border bg-background p-2 text-center">
                  <p className="text-lg font-bold text-primary">{stats?.items || 0}</p>
                  <p className="text-[10px] text-muted-foreground">Rules</p>
                </div>
                <div className="rounded-lg border border-border bg-background p-2 text-center">
                  <p className="text-lg font-bold">{stats?.categories || 0}</p>
                  <p className="text-[10px] text-muted-foreground">Categories</p>
                </div>
              </div>

              <div className="space-y-1.5">
                {repositories.map(repo => (
                  <Link key={repo.id} href={`/knowledge/detail?id=${repo.id}`}
                    className="block rounded-lg border border-border bg-background p-2.5 transition-colors hover:bg-accent/50">
                    <p className="text-xs font-semibold">{repo.name}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{repo.description}</p>
                  </Link>
                ))}
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <FileSearch className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs font-semibold">Search</span>
                </div>
                <div className="flex gap-1.5">
                  <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} onKeyDown={e => e.key === "Enter" && runSearch()}
                    placeholder="e.g. checkout..."
                    className="flex-1 rounded-lg border border-border bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary/40" />
                  <button onClick={runSearch} disabled={searching}
                    className="rounded-lg bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50">
                    {searching ? <Loader2 className="h-3 w-3 animate-spin" /> : "Go"}
                  </button>
                </div>
                {searchResults && (
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {searchResults.length === 0 && <p className="text-[10px] text-muted-foreground">No matches</p>}
                    {searchResults.map((hit, i) => (
                      <div key={i} className="rounded-lg border border-border/50 bg-background/50 p-2">
                        <p className="text-xs font-semibold">{hit.item.title}</p>
                        <p className="text-[10px] text-muted-foreground">{hit.repo_name} / {hit.category}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs font-semibold">Agent Briefing</span>
                </div>
                <div className="flex gap-1.5">
                  <textarea value={briefTask} onChange={e => setBriefTask(e.target.value)} placeholder="Paste a task..." rows={1}
                    className="flex-1 rounded-lg border border-border bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary/40 resize-none" />
                  <button onClick={runBriefing} disabled={briefingLoading}
                    className="rounded-lg bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50">
                    {briefingLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Brief"}
                  </button>
                </div>
                {briefing && (
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    <p className="text-[10px] text-muted-foreground">{briefing.summary}</p>
                    {briefing.items.map((h, i) => (
                      <div key={i} className="rounded-lg border border-border/50 bg-background/50 p-2">
                        <p className="text-xs font-semibold">{h.item.title}</p>
                        {h.item.rules.length > 0 && (
                          <ul className="mt-1 space-y-0.5">{h.item.rules.slice(0, 2).map((r, j) => <li key={j} className="text-[10px] text-muted-foreground">- {r}</li>)}</ul>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
