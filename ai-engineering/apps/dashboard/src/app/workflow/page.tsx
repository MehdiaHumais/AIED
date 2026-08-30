"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { useAuth } from "@/components/auth-provider"
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Edit3,
  FileText,
  Folder,
  Gavel,
  Loader2,
  Microscope,
  MousePointerClick,
  PencilRuler,
  Play,
  RefreshCw,
  Route,
  ShieldCheck,
  TrendingUp,
  Trash2,
  XCircle,
  Zap,
  Brain,
  Workflow,
  Database,
} from "lucide-react"
import { cn } from "@/lib/utils"

const API = "http://127.0.0.1:8001"

interface StageDef { key: string; name: string; layer: number; short: string }
interface RunSummary { id: string; name: string; request: string; status: string; stage_index: number; current_stage: string | null; approved_stages: number; total_stages: number; created_at: string; completed_at: string | null }
interface StageState { key: string; name: string; layer: number; status: string; item_id: string | null; board_review_id: string | null; request_sent: string; verdict: string | null; score: number | null; error: string; started_at: string | null; completed_at: string | null }
interface RunDetail { id: string; name: string; request: string; status: string; stage_index: number; stages: StageState[]; created_at: string; updated_at: string; completed_at: string | null; error: string }
interface WorkflowStats { total: number; running: number; needs_review: number; completed: number; failed: number; cancelled: number; stages: StageDef[] }

const stageIcons: Record<string, any> = {
  board: Gavel, research: Microscope, ux: MousePointerClick, design: PencilRuler,
  growth: TrendingUp, quality: ShieldCheck, intelligence: Brain, governance: Workflow, ekdt: Database,
}

const stageColors: Record<string, string> = {
  board: "var(--accent-purple)", research: "var(--accent-cyan)", ux: "#EC4899",
  design: "#F97316", growth: "var(--accent-green)", quality: "var(--accent-blue)",
  intelligence: "var(--accent-purple)", governance: "var(--accent-amber)", ekdt: "var(--accent-cyan)",
}

const statusConfig: Record<string, { symbol: string; color: string; bg: string; label: string }> = {
  pending:     { symbol: "○", color: "var(--text-muted)", bg: "transparent", label: "Queued" },
  running:     { symbol: "◉", color: "var(--accent-blue)", bg: "rgba(59,130,246,0.08)", label: "Running" },
  approved:    { symbol: "✓", color: "var(--accent-green)", bg: "rgba(34,197,94,0.08)", label: "Approved" },
  needs_review:{ symbol: "!", color: "var(--accent-amber)", bg: "rgba(245,158,11,0.08)", label: "Review" },
  failed:      { symbol: "✕", color: "var(--accent-red)", bg: "rgba(239,68,68,0.08)", label: "Failed" },
}

const runStatusStyle: Record<string, { bg: string; color: string }> = {
  running:     { bg: "rgba(59,130,246,0.1)", color: "var(--accent-blue)" },
  needs_review:{ bg: "rgba(245,158,11,0.1)", color: "var(--accent-amber)" },
  completed:   { bg: "rgba(34,197,94,0.1)", color: "var(--accent-green)" },
  failed:      { bg: "rgba(239,68,68,0.1)", color: "var(--accent-red)" },
  cancelled:   { bg: "rgba(100,116,139,0.1)", color: "var(--text-muted)" },
}

export default function WorkflowPage() {
  const { user } = useAuth()
  const [stats, setStats] = useState<WorkflowStats | null>(null)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [apiDown, setApiDown] = useState(false)
  const [nameText, setNameText] = useState("")
  const [requestText, setRequestText] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [editText, setEditText] = useState("")
  const [acting, setActing] = useState(false)
  const [lastAction, setLastAction] = useState("")
  const [buildFolder, setBuildFolder] = useState("")
  const [buildStarting, setBuildStarting] = useState(false)
  const [buildError, setBuildError] = useState("")

  const fetchOverview = () => {
    Promise.all([
      fetch(`${API}/api/workflow/stats`).then(r => r.json()),
      fetch(`${API}/api/workflow/runs`).then(r => r.json()),
    ]).then(([s, r]) => { setStats(s); setRuns(r.runs || []); setLoading(false); setApiDown(false) })
      .catch(() => { setLoading(false); setApiDown(true) })
  }

  useEffect(() => { fetchOverview() }, [])

  const loadDetail = (id: string) => {
    setDetailLoading(true)
    fetch(`${API}/api/workflow/runs/${id}`).then(r => r.json()).then(d => {
      const run = d.run; setDetail(run)
      if (run?.status === "needs_review") { const cur = run.stages[run.stage_index]; setEditText(cur?.request_sent || run.request || "") }
    }).catch(() => setDetail(null)).finally(() => setDetailLoading(false))
  }

  const pollRun = (runId: string, attempts = 0): Promise<void> => {
    return fetch(`${API}/api/workflow/runs/${runId}`).then(r => r.json()).then(d => {
      const run = d.run; setDetail(run)
      if (run && run.status !== "running") {
        if (run.status === "needs_review") { const cur = run.stages[run.stage_index]; setEditText(cur?.request_sent || run.request || "") }
        setLastAction(`Run ${run.status}: ${run.approved_stages ?? 0} of ${run.total_stages ?? 6} gates passed`)
        fetchOverview(); return
      }
      if (attempts > 18000) throw new Error("Timed out")
      return new Promise(r => setTimeout(r, 2000)).then(() => pollRun(runId, attempts + 1))
    })
  }

  const startRun = () => {
    if (!requestText.trim()) return
    setSubmitting(true); setSubmitError(""); setLastAction("")
    fetch(`${API}/api/workflow/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request: requestText.trim(), name: nameText.trim(), wait: false }) })
      .then(r => r.json()).then(async d => {
        if (d.error) throw new Error(d.error)
        const runId = d.run_id || d.run?.id; if (!runId) throw new Error("No run id")
        setSelectedId(runId); setDetail(d.run); setRequestText(""); setNameText(""); await pollRun(runId)
      }).catch(e => setSubmitError(e.message)).finally(() => setSubmitting(false))
  }

  const retryStage = () => {
    if (!selectedId || !editText.trim()) return; setActing(true); setLastAction("")
    fetch(`${API}/api/workflow/runs/${selectedId}/retry`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request: editText.trim(), wait: false }) })
      .then(r => r.json()).then(async d => { if (d.error) throw new Error(d.error); setLastAction("Retrying..."); await pollRun(selectedId) })
      .catch(e => setLastAction(`Retry failed: ${e.message}`)).finally(() => setActing(false))
  }

  const cancelRun = () => {
    if (!selectedId) return; setActing(true)
    fetch(`${API}/api/workflow/runs/${selectedId}/cancel`, { method: "POST" }).then(r => r.json())
      .then(d => { if (d.error) throw new Error(d.error); setLastAction("Cancelled"); loadDetail(selectedId); fetchOverview() })
      .catch(e => setLastAction(`Cancel failed: ${e.message}`)).finally(() => setActing(false))
  }

  const resumeRun = () => {
    if (!selectedId) return; setActing(true); setLastAction("")
    fetch(`${API}/api/workflow/runs/${selectedId}/resume`, { method: "POST" }).then(r => r.json())
      .then(async d => { if (d.error) throw new Error(d.error); setLastAction("Resuming..."); await pollRun(selectedId) })
      .catch(e => setLastAction(`Resume failed: ${e.message}`)).finally(() => setActing(false))
  }

  const deleteRun = (id: string) => {
    setActing(true)
    fetch(`${API}/api/workflow/runs/${id}`, { method: "DELETE" }).then(r => r.json())
      .then(d => { if (d.error) throw new Error(d.error); if (selectedId === id) { setSelectedId(null); setDetail(null) }; fetchOverview() })
      .catch(() => {}).finally(() => setActing(false))
  }

  const startBuild = () => {
    if (!selectedId || !buildFolder.trim()) return; setBuildStarting(true); setBuildError("")
    fetch(`${API}/api/workflow/runs/${selectedId}/start-build`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder: buildFolder.trim() }) })
      .then(r => r.json()).then(d => { if (d.error) throw new Error(d.error); window.location.href = `/monitor?task=${d.task_id}` })
      .catch(e => setBuildError(e.message)).finally(() => setBuildStarting(false))
  }

  const selectFolder = async () => {
    try {
      const uid = user?.id ? `?user_id=${user.id}` : ""
      const r = await fetch(`${API}/api/agent/select-folder${uid}`)
      const d = await r.json()
      if (d.path) setBuildFolder(d.path)
      else if (d.error) setBuildError(d.error)
    } catch {}
  }

  if (loading) return <DashboardLayout><div className="flex items-center justify-center h-64"><p style={{ color: "var(--text-muted)" }}>Loading pipeline...</p></div></DashboardLayout>
  if (apiDown) return <DashboardLayout><div className="flex items-center justify-center h-64"><div className="text-center"><p className="text-[18px] font-semibold mb-2" style={{ color: "var(--text-primary)" }}>API Offline</p><p className="text-[13px]" style={{ color: "var(--text-muted)" }}>Start: <code className="px-1.5 py-0.5 rounded" style={{ background: "var(--bg-elevated)" }}>py -m apps.api.main</code></p></div></div></DashboardLayout>

  const stageChain = stats?.stages ?? []

  return (
    <DashboardLayout>
      <div className="max-w-[1400px] space-y-8 animate-fade-in">
        {/* Header */}
        <div>
          <h1 className="text-[28px] font-bold tracking-tight flex items-center gap-3" style={{ color: "var(--text-primary)" }}>
            <Route className="h-7 w-7" style={{ color: "var(--accent-purple)" }} />
            Workflow Pipeline
          </h1>
          <p className="text-[14px] mt-1 max-w-2xl" style={{ color: "var(--text-secondary)" }}>
            Cross-layer orchestration from Idea through 10 AI engineering layers. Each gate reviews and approves before auto-advancing.
          </p>
        </div>

        {/* Visual Pipeline */}
        {stageChain.length > 0 && (
          <div className="card-elevated p-6">
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] mb-4" style={{ color: "var(--text-muted)" }}>Pipeline Architecture</p>
            <div className="flex items-stretch gap-0 overflow-x-auto pb-2">
              {stageChain.map((stage, i) => {
                const Icon = stageIcons[stage.key] || FileText
                const color = stageColors[stage.key] || "var(--accent-blue)"
                return (
                  <div key={stage.key} className="flex items-center shrink-0">
                    <div className="flex flex-col items-center text-center min-w-[110px]">
                      <div className="h-10 w-10 rounded-xl flex items-center justify-center mb-2" style={{ background: `${color}15`, border: `1px solid ${color}30` }}>
                        <Icon className="h-5 w-5" style={{ color }} />
                      </div>
                      <p className="text-[11px] font-bold" style={{ color }}>L{stage.layer}</p>
                      <p className="text-[11px] font-semibold mt-0.5" style={{ color: "var(--text-primary)" }}>{stage.short}</p>
                    </div>
                    {i < stageChain.length - 1 && (
                      <div className="flex items-center px-1">
                        <div className="w-8 h-px" style={{ background: "var(--border-default)" }} />
                        <ArrowRight className="h-3 w-3 shrink-0" style={{ color: "var(--text-muted)", opacity: 0.4 }} />
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* KPI Row */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[
            { label: "TOTAL", value: stats?.total ?? 0, color: "var(--text-primary)" },
            { label: "RUNNING", value: stats?.running ?? 0, color: "var(--accent-blue)" },
            { label: "REVIEW", value: stats?.needs_review ?? 0, color: "var(--accent-amber)" },
            { label: "COMPLETED", value: stats?.completed ?? 0, color: "var(--accent-green)" },
            { label: "FAILED", value: stats?.failed ?? 0, color: "var(--accent-red)" },
          ].map(k => (
            <div key={k.label} className="card-depth p-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em]" style={{ color: "var(--text-muted)" }}>{k.label}</p>
              <p className="text-[28px] font-bold mt-1" style={{ color: k.color }}>{k.value}</p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-6">
          {/* Left: Start + Runs */}
          <div className="space-y-4">
            {/* Start form */}
            <div className="card-depth p-5">
              <p className="text-[13px] font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
                <Zap className="h-4 w-4" style={{ color: "var(--accent-purple)" }} /> Start Pipeline
              </p>
              <div className="space-y-3">
                <input value={nameText} onChange={e => setNameText(e.target.value)} placeholder="Run name (optional)"
                  className="w-full rounded-lg px-3 py-2.5 text-[13px] focus:outline-none focus:ring-1 transition-colors"
                  style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }} />
                <textarea value={requestText} onChange={e => setRequestText(e.target.value)} placeholder="Describe your project idea..." rows={4}
                  className="w-full rounded-lg px-3 py-2.5 text-[13px] min-h-[100px] focus:outline-none focus:ring-1 transition-colors resize-none"
                  style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }} />
                <button onClick={startRun} disabled={submitting || !requestText.trim()}
                  className="w-full flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
                  style={{ background: "var(--accent-purple)", boxShadow: "0 0 16px rgba(139,92,246,0.25)" }}>
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                  Start at Layer 2
                </button>
                {submitError && <p className="text-[11px]" style={{ color: "var(--accent-red)" }}>{submitError}</p>}
              </div>
            </div>

            {/* Runs list */}
            <div className="card-depth p-5">
              <p className="text-[13px] font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Pipeline Runs</p>
              {runs.length === 0 ? (
                <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>No runs yet</p>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {runs.map(run => {
                    const rs = runStatusStyle[run.status] || runStatusStyle.cancelled
                    return (
                      <button key={run.id} onClick={() => { setSelectedId(run.id); loadDetail(run.id) }}
                        className="w-full text-left rounded-lg p-3 transition-all"
                        style={{
                          background: selectedId === run.id ? "rgba(139,92,246,0.08)" : "var(--bg-elevated)",
                          border: `1px solid ${selectedId === run.id ? "rgba(139,92,246,0.3)" : "var(--border-subtle)"}`,
                        }}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[12px] font-semibold truncate" style={{ color: "var(--text-primary)" }}>{run.name}</span>
                          <span className="text-[9px] font-bold px-2 py-0.5 rounded-full shrink-0" style={{ background: rs.bg, color: rs.color }}>{run.status}</span>
                        </div>
                        <p className="text-[11px] truncate mt-1" style={{ color: "var(--text-muted)" }}>{run.request}</p>
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{run.current_stage || "—"}</span>
                          <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{run.approved_stages}/{run.total_stages} gates</span>
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right: Detail */}
          <div className="space-y-4">
            {!selectedId || !detail ? (
              <div className="card-depth p-12 text-center" style={{ borderStyle: "dashed" }}>
                {detailLoading ? (
                  <p className="flex items-center justify-center gap-2 text-[13px]" style={{ color: "var(--text-muted)" }}><Loader2 className="h-4 w-4 animate-spin" /> Loading...</p>
                ) : (
                  <p className="text-[13px]" style={{ color: "var(--text-muted)" }}>Select a run to see gate-by-gate progress</p>
                )}
              </div>
            ) : (
              <>
                {/* Run header */}
                <div className="card-depth p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-[16px] font-bold" style={{ color: "var(--text-primary)" }}>{detail.name}</h3>
                        <span className="text-[9px] font-bold px-2 py-0.5 rounded-full" style={{ background: (runStatusStyle[detail.status] || runStatusStyle.cancelled).bg, color: (runStatusStyle[detail.status] || runStatusStyle.cancelled).color }}>{detail.status}</span>
                      </div>
                      <p className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>Started {new Date(detail.created_at).toLocaleString()}</p>
                    </div>
                    <div className="flex gap-2">
                      {detail.status === "running" && (
                        <button onClick={cancelRun} disabled={acting} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold transition-colors" style={{ border: "1px solid rgba(239,68,68,0.3)", color: "var(--accent-red)" }}
                          onMouseEnter={e => e.currentTarget.style.background = "rgba(239,68,68,0.08)"} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                          <XCircle className="h-3 w-3" /> Cancel
                        </button>
                      )}
                      <button onClick={() => deleteRun(detail.id)} disabled={acting} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold transition-colors" style={{ border: "1px solid var(--border-default)", color: "var(--text-muted)" }}
                        onMouseEnter={e => e.currentTarget.style.background = "var(--bg-hover)"} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                        <Trash2 className="h-3 w-3" /> Delete
                      </button>
                    </div>
                  </div>
                  {lastAction && <p className="text-[11px] mt-3" style={{ color: "var(--text-muted)" }}>{lastAction}</p>}
                </div>

                {/* Stage cards — visual pipeline */}
                <div className="space-y-2">
                  {detail.stages.map((stage, i) => {
                    const Icon = stageIcons[stage.key] || FileText
                    const color = stageColors[stage.key] || "var(--accent-blue)"
                    const sc = statusConfig[stage.status] || statusConfig.pending
                    const isCurrent = i === detail.stage_index && detail.status === "running"
                    return (
                      <div key={stage.key} className="card-depth p-4 transition-all" style={isCurrent ? { border: `1px solid rgba(59,130,246,0.3)`, boxShadow: "0 0 12px rgba(59,130,246,0.08)" } : {}}>
                        <div className="flex items-center gap-4">
                          {/* Pipeline position */}
                          <div className="flex flex-col items-center shrink-0">
                            <div className="h-8 w-8 rounded-lg flex items-center justify-center" style={{ background: `${color}15`, border: `1px solid ${color}30` }}>
                              <Icon className="h-4 w-4" style={{ color }} />
                            </div>
                            {i < detail.stages.length - 1 && (
                              <div className="w-px h-3 mt-1" style={{ background: "var(--border-default)" }} />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>{stage.name}</span>
                              <span className="text-[9px] font-medium px-1.5 py-0.5 rounded" style={{ background: "var(--bg-hover)", color: "var(--text-muted)" }}>Layer {stage.layer}</span>
                            </div>
                            <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                              {stage.board_review_id ? `Review ${stage.board_review_id.slice(0, 8)} · Score ${stage.score ?? "—"}` : "Not yet submitted"}
                            </p>
                            {stage.status === "running" && (
                              <p className="text-[11px] mt-2 flex items-center gap-1.5" style={{ color: "var(--accent-blue)" }}>
                                <Loader2 className="h-3 w-3 animate-spin" /> Processing...
                              </p>
                            )}
                            {stage.status === "approved" && (
                              <p className="text-[11px] mt-2 flex items-center gap-1.5" style={{ color: "var(--accent-green)" }}>
                                <CheckCircle2 className="h-3 w-3" /> Approved (score {stage.score ?? "—"})
                              </p>
                            )}
                            {stage.error && <p className="text-[11px] mt-2" style={{ color: "var(--accent-red)" }}>{stage.error}</p>}
                          </div>
                          <div className="shrink-0">
                            <span className="text-[10px] font-bold px-2.5 py-1 rounded-lg" style={{ background: sc.bg, color: sc.color }}>{sc.label}</span>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>

                {/* Edit/Retry panel */}
                {detail.status === "needs_review" && (
                  <div className="card-depth p-5" style={{ border: "1px solid rgba(245,158,11,0.3)", background: "rgba(245,158,11,0.04)" }}>
                    <p className="text-[13px] font-semibold flex items-center gap-2 mb-2" style={{ color: "var(--accent-amber)" }}>
                      <Edit3 className="h-4 w-4" /> Edit & Retry
                    </p>
                    <p className="text-[11px] mb-3" style={{ color: "var(--text-muted)" }}>The board rejected this gate. Edit the request and retry — approved work is kept.</p>
                    <textarea value={editText} onChange={e => setEditText(e.target.value)} rows={5}
                      className="w-full rounded-lg px-3 py-2.5 text-[13px] focus:outline-none focus:ring-1 resize-none"
                      style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }} />
                    <div className="flex gap-2 mt-3">
                      <button onClick={retryStage} disabled={acting || !editText.trim()}
                        className="flex items-center gap-2 rounded-lg px-4 py-2 text-[12px] font-semibold text-black transition-all hover:opacity-90 disabled:opacity-50"
                        style={{ background: "var(--accent-amber)" }}>
                        {acting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Retry
                      </button>
                      <button onClick={cancelRun} disabled={acting}
                        className="flex items-center gap-2 rounded-lg px-4 py-2 text-[12px] font-semibold transition-colors"
                        style={{ border: "1px solid rgba(239,68,68,0.3)", color: "var(--accent-red)" }}>
                        <XCircle className="h-3.5 w-3.5" /> Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* Completed */}
                {detail.status === "completed" && (
                  <div className="card-depth p-5" style={{ border: "1px solid rgba(34,197,94,0.3)", background: "rgba(34,197,94,0.04)" }}>
                    <p className="text-[14px] font-semibold flex items-center gap-2" style={{ color: "var(--accent-green)" }}>
                      <CheckCircle2 className="h-5 w-5" /> Pipeline Complete
                    </p>
                    <p className="text-[12px] mt-1 mb-4" style={{ color: "var(--text-muted)" }}>All gates approved. Choose a folder and start the build.</p>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <button onClick={selectFolder} disabled={buildStarting}
                        className="flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[12px] font-semibold transition-colors shrink-0"
                        style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
                        <Folder className="h-3.5 w-3.5" /> Select
                      </button>
                      <input value={buildFolder} onChange={e => setBuildFolder(e.target.value)} placeholder="Project folder path"
                        className="flex-1 rounded-lg px-3 py-2.5 text-[12px]"
                        style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }} />
                      <button onClick={startBuild} disabled={buildStarting || !buildFolder.trim()}
                        className="flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[12px] font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
                        style={{ background: "var(--accent-green)" }}>
                        {buildStarting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Build
                      </button>
                    </div>
                    {buildError && <p className="text-[11px] mt-2" style={{ color: "var(--accent-red)" }}>{buildError}</p>}
                  </div>
                )}

                {/* Failed */}
                {detail.status === "failed" && (
                  <div className="card-depth p-5" style={{ border: "1px solid rgba(239,68,68,0.3)", background: "rgba(239,68,68,0.04)" }}>
                    <p className="text-[14px] font-semibold flex items-center gap-2" style={{ color: "var(--accent-red)" }}>
                      <XCircle className="h-5 w-5" /> Run Failed
                    </p>
                    <p className="text-[12px] mt-1 mb-3" style={{ color: "var(--text-muted)" }}>{detail.error || "A stage could not complete."}</p>
                    <button onClick={resumeRun} disabled={acting}
                      className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-[12px] font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
                      style={{ background: "var(--accent-red)" }}>
                      {acting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Resume from failed gate
                    </button>
                  </div>
                )}

                {detail.status === "cancelled" && (
                  <div className="card-depth p-5" style={{ border: "1px solid var(--border-default)" }}>
                    <p className="text-[13px] font-semibold" style={{ color: "var(--text-muted)" }}>Run cancelled</p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  )
}
