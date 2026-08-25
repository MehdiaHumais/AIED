"use client"

import { useEffect, useState, useRef } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { Bot, Send, StopCircle, FolderOpen, X, Loader2, CheckCircle2, Terminal, FileCode2, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"

const API = "http://127.0.0.1:8001"

interface Agent { id: string; name: string; role: string; department: string; model: string; capabilities: string[]; status: string; tasks_completed: number; tasks_failed: number; current_task: string | null }
interface ChatMessage { role: "user" | "agent"; content: string; timestamp: string; files_written?: { path: string; size: number }[]; commands_run?: { command: string; stdout: string; stderr: string; returncode: number; error?: string }[]; errors?: { path: string; error: string }[] }

const statusCfg: Record<string, { symbol: string; color: string; bg: string; label: string; pulse: boolean }> = {
  working: { symbol: "◉", color: "var(--accent-blue)", bg: "rgba(59,130,246,0.1)", label: "Running", pulse: true },
  idle:    { symbol: "○", color: "var(--text-muted)", bg: "transparent", label: "Idle", pulse: false },
  waiting: { symbol: "◌", color: "var(--accent-amber)", bg: "rgba(245,158,11,0.1)", label: "Waiting", pulse: false },
  error:   { symbol: "✕", color: "var(--accent-red)", bg: "rgba(239,68,68,0.1)", label: "Error", pulse: false },
  offline: { symbol: "○", color: "var(--text-muted)", bg: "transparent", label: "Offline", pulse: false },
}

const deptAccent: Record<string, string> = {
  "Executive Office": "var(--accent-purple)", "Engineering Office": "var(--accent-blue)",
  "Product Office": "var(--accent-green)", "Architecture Office": "var(--accent-cyan)",
  "Development Office": "var(--accent-blue)", "UX Office": "#EC4899",
  "Quality Office": "var(--accent-amber)", "DevOps Office": "#F97316",
  "Intelligence Office": "var(--accent-purple)",
}

function renderMarkdown(text: string): string {
  return text
    .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="rounded-lg p-3 my-2 text-[12px] overflow-x-auto" style="background:var(--bg-elevated);color:var(--accent-green)"><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded text-[12px]" style="background:var(--bg-elevated);color:var(--accent-purple)">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>')
    .replace(/^### (.+)$/gm, '<h3 class="text-[15px] font-bold mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-[17px] font-bold mt-5 mb-2">$1</h2>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc text-[13px]">$1</li>')
    .replace(/\n\n/g, '<br/>').replace(/\n/g, '<br/>')
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Agent | null>(null)
  const [chatMsg, setChatMsg] = useState("")
  const [chatHistory, setChatHistory] = useState<Record<string, ChatMessage[]>>({})
  const [chatting, setChatting] = useState(false)
  const [chatStep, setChatStep] = useState("")
  const [filterDept, setFilterDept] = useState("")
  const [projectDir, setProjectDir] = useState("")
  const [autoMode, setAutoMode] = useState(true)
  const [showBrowser, setShowBrowser] = useState(false)
  const [browserFolders, setBrowserFolders] = useState<{ name: string; path: string }[]>([])
  const [browserParent, setBrowserParent] = useState("")
  const [browserPath, setBrowserPath] = useState("")
  const chatEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => { fetch(`${API}/api/agents`).then(r => r.json()).then(d => { setAgents(d.agents || []); setLoading(false) }).catch(() => setLoading(false)) }, [])
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }) }, [chatHistory])

  const openBrowser = async (startPath?: string) => {
    setShowBrowser(true); setBrowserFolders([])
    try { const r = await fetch(startPath ? `${API}/api/files/browse?path=${encodeURIComponent(startPath)}` : `${API}/api/files/browse`); const d = await r.json(); setBrowserFolders(d.folders || []); setBrowserParent(d.parent || ""); setBrowserPath(d.current_path || "") } catch {}
  }

  const stopAgent = () => { abortRef.current?.abort(); setChatting(false); setChatStep("") }

  const sendChat = async () => {
    if (!selected || !chatMsg.trim()) return
    const userMsg = chatMsg.trim(); setChatMsg(""); setChatting(true); setChatStep("Thinking...")
    const ctrl = new AbortController(); abortRef.current = ctrl
    const history = chatHistory[selected.id] || []
    setChatHistory(p => ({ ...p, [selected.id]: [...history, { role: "user", content: userMsg, timestamp: new Date().toLocaleTimeString() }] }))
    try {
      const url = autoMode ? `${API}/api/agents/${selected.id}/auto-execute` : `${API}/api/agents/${selected.id}/chat`
      const body = autoMode ? { message: userMsg, project_dir: projectDir || undefined } : { message: userMsg }
      setChatStep(autoMode ? "Executing..." : "Generating...")
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctrl.signal })
      const d = await r.json()
      setChatHistory(p => ({ ...p, [selected.id]: [...(p[selected.id] || []), { role: "agent", content: d.response || d.error || "No response", timestamp: new Date().toLocaleTimeString(), files_written: d.files_written, commands_run: d.commands_run, errors: d.errors }] }))
    } catch (e: any) {
      if (e.name !== "AbortError") setChatHistory(p => ({ ...p, [selected.id]: [...(p[selected.id] || []), { role: "agent", content: `Error: ${e.message}`, timestamp: new Date().toLocaleTimeString() }] }))
    }
    abortRef.current = null; setChatStep(""); setChatting(false)
  }

  const departments = [...new Set(agents.map(a => a.department))]
  const filtered = filterDept ? agents.filter(a => a.department === filterDept) : agents
  const grouped = filtered.reduce((acc, a) => { if (!acc[a.department]) acc[a.department] = []; acc[a.department].push(a); return acc }, {} as Record<string, Agent[]>)
  const activeCount = agents.filter(a => a.status === "working").length
  const currentHistory = selected ? chatHistory[selected.id] || [] : []

  return (
    <DashboardLayout>
      <div className="max-w-[1400px] space-y-6 animate-fade-in">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-[28px] font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>AI Agents</h1>
            <p className="text-[14px] mt-1" style={{ color: "var(--text-secondary)" }}>
              {agents.length} agents across {departments.length} offices — {activeCount} currently active
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-[12px]" style={{ color: "var(--text-muted)" }}>
              <span className="status-dot status-running" /> {activeCount} running
            </span>
            <span className="flex items-center gap-1.5 text-[12px]" style={{ color: "var(--text-muted)" }}>
              <span className="status-dot status-queued" /> {agents.length - activeCount} idle
            </span>
          </div>
        </div>

        {/* Project dir */}
        <div className="card-depth p-4">
          <label className="text-[11px] font-semibold uppercase tracking-[0.08em] mb-2 block" style={{ color: "var(--text-muted)" }}>Project Folder</label>
          <div className="flex gap-2">
            <input value={projectDir} onChange={e => setProjectDir(e.target.value)} placeholder="Paste a path or click Browse..."
              className="flex-1 rounded-lg px-3 py-2 text-[13px]"
              style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }} />
            <button onClick={() => openBrowser()} className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-[12px] font-semibold transition-colors"
              style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
              <FolderOpen className="h-3.5 w-3.5" /> Browse
            </button>
            {projectDir && <button onClick={() => setProjectDir("")} className="rounded-lg px-2 py-2" style={{ color: "var(--text-muted)" }}><X className="h-4 w-4" /></button>}
          </div>
          {projectDir && <p className="text-[11px] mt-1.5 font-mono" style={{ color: "var(--accent-green)" }}>{projectDir}</p>}
        </div>

        {/* Folder browser modal */}
        {showBrowser && (
          <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }} onClick={() => setShowBrowser(false)}>
            <div className="rounded-2xl w-full max-w-lg max-h-[70vh] flex flex-col shadow-2xl animate-slide-up" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)" }} onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                <p className="text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>Select Folder</p>
                <button onClick={() => setShowBrowser(false)} style={{ color: "var(--text-muted)" }}><X className="h-4 w-4" /></button>
              </div>
              <div className="px-4 py-2 flex items-center gap-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                {browserParent && <button onClick={() => openBrowser(browserParent)} className="text-[11px] px-2 py-1 rounded" style={{ background: "var(--bg-hover)", color: "var(--text-secondary)" }}>← Back</button>}
                <span className="text-[12px] font-mono truncate" style={{ color: "var(--text-muted)" }}>{browserPath || "Select a drive"}</span>
              </div>
              <div className="flex-1 overflow-y-auto p-2">
                {browserFolders.length === 0 ? <p className="text-center py-8 text-[12px]" style={{ color: "var(--text-muted)" }}>No folders</p> : (
                  browserFolders.map(f => (
                    <div key={f.path} className="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer group transition-colors"
                      style={{ color: "var(--text-secondary)" }}
                      onDoubleClick={() => openBrowser(f.path)}
                      onMouseEnter={e => e.currentTarget.style.background = "var(--bg-hover)"} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                      <FolderOpen className="h-4 w-4 shrink-0" style={{ opacity: 0.5 }} />
                      <span className="flex-1 truncate text-[12px]">{f.name}</span>
                      <button onClick={e => { e.stopPropagation(); setProjectDir(f.path); setShowBrowser(false) }}
                        className="text-[10px] px-2 py-0.5 rounded font-semibold opacity-0 group-hover:opacity-100 transition-opacity"
                        style={{ background: "var(--accent-blue)", color: "white" }}>Select</button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* Filter */}
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => setFilterDept("")} className="rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors"
            style={!filterDept ? { background: "var(--accent-blue)", color: "white" } : { background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border-subtle)" }}>
            All
          </button>
          {departments.map(d => (
            <button key={d} onClick={() => setFilterDept(d)} className="rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors"
              style={filterDept === d ? { background: "var(--accent-blue)", color: "white" } : { background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border-subtle)" }}>
              {d}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-40"><Loader2 className="h-6 w-6 animate-spin" style={{ color: "var(--text-muted)" }} /></div>
        ) : (
          <div className="space-y-6">
            {Object.entries(grouped).map(([dept, deptAgents]) => {
              const ac = deptAccent[dept] || "var(--accent-blue)"
              return (
                <div key={dept}>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="h-2 w-2 rounded-full" style={{ background: ac }} />
                    <p className="text-[12px] font-bold uppercase tracking-[0.06em]" style={{ color: ac }}>{dept}</p>
                    <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>({deptAgents.length})</span>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                    {deptAgents.map(agent => {
                      const sc = statusCfg[agent.status] || statusCfg.idle
                      const isSelected = selected?.id === agent.id
                      return (
                        <div key={agent.id} onClick={() => setSelected(isSelected ? null : agent)}
                          className="card-depth p-4 cursor-pointer transition-all hover:scale-[1.005]"
                          style={isSelected ? { border: `1px solid ${ac}40`, boxShadow: `0 0 16px ${ac}10` } : {}}>
                          {/* Agent header */}
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex items-center gap-2.5">
                              <div className="relative">
                                <div className="h-9 w-9 rounded-lg flex items-center justify-center text-[13px] font-bold" style={{ background: `${ac}15`, color: ac }}>
                                  {agent.name[0]}
                                </div>
                                <div className={cn("absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2", `status-${agent.status === "working" ? "running" : agent.status === "idle" ? "queued" : "failed"}`)}
                                  style={{ borderColor: "var(--bg-surface)" }} />
                              </div>
                              <div>
                                <p className="text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>{agent.name}</p>
                                <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{agent.role}</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full" style={{ background: sc.bg }}>
                              <span className={cn("text-[10px] font-bold", sc.pulse && "animate-pulse")} style={{ color: sc.color }}>{sc.symbol}</span>
                              <span className="text-[9px] font-semibold" style={{ color: sc.color }}>{sc.label}</span>
                            </div>
                          </div>

                          {/* Current task */}
                          {agent.current_task && (
                            <div className="mb-3 rounded-lg px-3 py-2" style={{ background: "var(--bg-elevated)" }}>
                              <p className="text-[10px] font-semibold uppercase tracking-[0.06em] mb-0.5" style={{ color: "var(--text-muted)" }}>Current Task</p>
                              <p className="text-[11px] truncate" style={{ color: "var(--accent-blue)" }}>{agent.current_task}</p>
                            </div>
                          )}

                          {/* Model + stats */}
                          <div className="flex items-center justify-between text-[10px]" style={{ color: "var(--text-muted)" }}>
                            <span className="font-mono">{agent.model}</span>
                            <span>{agent.tasks_completed} done · {agent.tasks_failed} fail</span>
                          </div>

                          {/* Capabilities */}
                          {agent.capabilities.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {agent.capabilities.slice(0, 3).map(c => (
                                <span key={c} className="rounded px-1.5 py-0.5 text-[9px] font-medium" style={{ background: "var(--bg-hover)", color: "var(--text-muted)" }}>{c}</span>
                              ))}
                              {agent.capabilities.length > 3 && <span className="text-[9px]" style={{ color: "var(--text-muted)" }}>+{agent.capabilities.length - 3}</span>}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Chat panel */}
        {selected && (
          <div className="card-depth overflow-hidden animate-slide-up">
            <div className="px-5 py-4 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
              <div className="flex items-center gap-2">
                <Bot className="h-4 w-4" style={{ color: deptAccent[selected.department] || "var(--accent-blue)" }} />
                <p className="text-[14px] font-semibold" style={{ color: "var(--text-primary)" }}>Chat with {selected.name}</p>
                {chatting && <span className="text-[10px] font-medium px-2 py-0.5 rounded-full animate-pulse" style={{ background: "rgba(59,130,246,0.1)", color: "var(--accent-blue)" }}>{chatStep}</span>}
              </div>
              <div className="flex items-center gap-2">
                {currentHistory.length > 0 && (
                  <button onClick={() => setChatHistory(p => ({ ...p, [selected.id]: [] }))} className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>Clear</button>
                )}
                <button onClick={() => setSelected(null)} style={{ color: "var(--text-muted)" }}><X className="h-4 w-4" /></button>
              </div>
            </div>

            {/* Messages */}
            {currentHistory.length > 0 && (
              <div className="max-h-[400px] overflow-y-auto p-4 space-y-4">
                {currentHistory.map((msg, i) => (
                  <div key={i} className={msg.role === "user" ? "flex justify-end" : ""}>
                    <div className={cn("max-w-[80%]", msg.role === "user" ? "" : "")}>
                      <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-muted)" }}>
                        {msg.role === "user" ? "You" : selected.name} · {msg.timestamp}
                      </p>
                      {msg.role === "agent" ? (
                        <div className="space-y-2">
                          <div className="rounded-xl px-4 py-3 text-[13px] leading-relaxed" style={{ background: "var(--bg-elevated)", color: "var(--text-primary)" }}
                            dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                          {msg.files_written && msg.files_written.length > 0 && (
                            <div className="rounded-lg px-3 py-2" style={{ background: "rgba(34,197,94,0.06)", border: "1px solid rgba(34,197,94,0.2)" }}>
                              <p className="text-[10px] font-semibold mb-1 flex items-center gap-1" style={{ color: "var(--accent-green)" }}><FileCode2 className="h-3 w-3" /> {msg.files_written.length} files written</p>
                              {msg.files_written.map((f, fi) => <p key={fi} className="text-[10px] font-mono" style={{ color: "var(--accent-green)", opacity: 0.8 }}>{f.path}</p>)}
                            </div>
                          )}
                          {msg.commands_run && msg.commands_run.length > 0 && (
                            <div className="rounded-lg px-3 py-2" style={{ background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.2)" }}>
                              <p className="text-[10px] font-semibold mb-1 flex items-center gap-1" style={{ color: "var(--accent-blue)" }}><Terminal className="h-3 w-3" /> {msg.commands_run.length} commands</p>
                              {msg.commands_run.map((c, ci) => (
                                <div key={ci}>
                                  <p className="text-[10px] font-mono" style={{ color: "var(--accent-blue)" }}>$ {c.command}</p>
                                  {c.stderr && <pre className="text-[10px] font-mono mt-1 p-2 rounded" style={{ background: "var(--bg-elevated)", color: "var(--accent-red)" }}>{c.stderr.slice(0, 300)}</pre>}
                                </div>
                              ))}
                            </div>
                          )}
                          {msg.errors && msg.errors.length > 0 && (
                            <div className="rounded-lg px-3 py-2" style={{ background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.2)" }}>
                              <p className="text-[10px] font-semibold flex items-center gap-1" style={{ color: "var(--accent-red)" }}><AlertCircle className="h-3 w-3" /> Errors</p>
                              {msg.errors.map((e, ei) => <p key={ei} className="text-[10px] font-mono" style={{ color: "var(--accent-red)" }}>{e.path}: {e.error}</p>)}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="rounded-xl px-4 py-3 text-[13px]" style={{ background: "var(--accent-blue)", color: "white" }}>{msg.content}</div>
                      )}
                    </div>
                  </div>
                ))}
                {chatting && (
                  <div className="flex items-center gap-2" style={{ color: "var(--accent-blue)" }}>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span className="text-[12px]">{chatStep}</span>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}

            {/* Input — AI workspace style */}
            <div className="p-4" style={{ borderTop: "1px solid var(--border-subtle)", background: "var(--bg-surface)" }}>
              <div className="rounded-xl overflow-hidden" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)" }}>
                <textarea value={chatMsg} onChange={e => setChatMsg(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat() } }}
                  placeholder={autoMode ? `Tell ${selected.name} to build something — it will write files and run commands...` : `Ask ${selected.name} anything...`}
                  className="w-full bg-transparent px-4 pt-4 pb-2 text-[13px] resize-none outline-none"
                  style={{ color: "var(--text-primary)", minHeight: "80px" }} />
                <div className="flex items-center justify-between px-4 py-2.5" style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  <div className="flex items-center gap-3">
                    <label className="flex items-center gap-1.5 text-[11px] cursor-pointer" style={{ color: "var(--text-muted)" }}>
                      <input type="checkbox" checked={autoMode} onChange={e => setAutoMode(e.target.checked)} className="rounded" />
                      Auto-execute
                    </label>
                    <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>Enter to send · Shift+Enter for newline</span>
                  </div>
                  {chatting ? (
                    <button onClick={stopAgent} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold transition-colors"
                      style={{ background: "rgba(239,68,68,0.1)", color: "var(--accent-red)" }}>
                      <StopCircle className="h-3.5 w-3.5" /> Stop
                    </button>
                  ) : (
                    <button onClick={sendChat} disabled={!chatMsg.trim()}
                      className="flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-[12px] font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
                      style={{ background: "var(--accent-blue)" }}>
                      <Send className="h-3.5 w-3.5" /> Run
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
