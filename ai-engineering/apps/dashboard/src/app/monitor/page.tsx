"use client"

import { useEffect, useState, useRef, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { DashboardLayout } from "@/components/layout/dashboard-layout"

interface PipelineStatus {
  task_id: string
  project_id: string
  title: string
  description: string
  stage: string
  plan_content: string
  build_output: string
  check_output: string
  error: string
  deploy_output: string
  files_written: { path: string; size: number }[]
  commands_run: { command: string; stdout: string; stderr: string; returncode: number }[]
  history: { stage: string; message: string; timestamp: string }[]
  project_mode: string
  project_name: string
  project_folder: string
  prebuilt_action: string
  current_agent: string
  current_action: string
  todo_list: { id: number; description: string; details: string; source: string; status: string }[]
  analysis_report: string
  task_mode?: string
  test_report?: any
}

const stageColors: Record<string, string> = {
  idle: "bg-gray-500/10 text-gray-400 border-gray-500/30",
  planning: "bg-purple-500/10 text-purple-400 border-purple-500/30",
  awaiting_plan_approval: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  building: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  checking: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  awaiting_check_approval: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  deploying: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
  completed: "bg-green-500/10 text-green-400 border-green-500/30",
  failed: "bg-red-500/10 text-red-400 border-red-500/30",
  awaiting_prebuilt_action: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  analyzing: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  fixing: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  testing: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  test_failed: "bg-rose-500/10 text-rose-400 border-rose-500/30",
}

const stageLabels: Record<string, string> = {
  idle: "Ready",
  planning: "Planning...",
  awaiting_plan_approval: "Awaiting Your Approval",
  building: "Building...",
  checking: "Validating...",
  awaiting_check_approval: "Ready to Deploy",
  deploying: "Deploying...",
  completed: "Completed",
  failed: "Failed",
  awaiting_prebuilt_action: "Choose Action",
  analyzing: "Analyzing...",
  fixing: "Fixing Issues...",
  testing: "Testing...",
  test_failed: "Issues Found",
}

const stageIcons: Record<string, string> = {
  idle: "[ ]",
  planning: "[~]",
  awaiting_plan_approval: "[!]",
  building: "[*]",
  checking: "[?]",
  awaiting_check_approval: "[!]",
  deploying: "[^]",
  completed: "[OK]",
  failed: "[!!]",
  awaiting_prebuilt_action: "[?]",
  analyzing: "[...]",
  fixing: "[fix]",
  testing: "[test]",
  test_failed: "[!!]",
}

const STAGE_ORDER = ["planning", "awaiting_plan_approval", "building", "checking", "awaiting_check_approval", "deploying", "completed"]

function formatMd(text: string): string {
  return text
    .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="bg-muted text-green-400 rounded-lg p-3 my-2 text-xs overflow-x-auto"><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-secondary px-1 py-0.5 rounded text-xs text-pink-400">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>')
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-bold mt-3 mb-1 text-foreground">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-bold mt-4 mb-1 text-foreground">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-lg font-bold mt-5 mb-2 text-foreground">$1</h1>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc text-xs">$1</li>')
    .replace(/\n\n/g, '<br/>')
    .replace(/\n/g, '<br/>')
}

function getProgress(stage: string): number {
  const idx = STAGE_ORDER.indexOf(stage)
  if (idx < 0) return 0
  if (stage === "completed") return 100
  if (stage === "failed") return 100
  return Math.round(((idx + 0.5) / STAGE_ORDER.length) * 100)
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString()
  } catch {
    return ""
  }
}

// Derive "how to run" instructions from the commands the agent actually ran.
function buildRunInstructions(p: PipelineStatus): { folder: string; commands: string[]; url?: string } | null {
  if (!p || !p.commands_run || p.commands_run.length === 0) return null
  const cmds = p.commands_run.filter((c) => c && c.command)
  if (cmds.length === 0) return null

  // The agent typically runs a build then a start. Prefer the last start/dev command.
  const isStart = (cmd: string) =>
    /npm (run )?(start|dev|preview|serve)\b/.test(cmd) ||
    /node /.test(cmd) ||
    /py |python /.test(cmd) ||
    /flutter run/.test(cmd) ||
    /uvicorn|gunicorn/.test(cmd)

  let runCmd = cmds.map((c) => c.command).filter(isStart).pop()
  if (!runCmd) {
    const first = cmds[0]
    runCmd = first.command
  }

  // Normalize to the least surprising start command for web apps.
  const scripts = runCmd.match(/npm run (dev|dev:.*|start|preview|serve|build)\b/)
  if (scripts && p.project_folder) {
    const script = scripts[1]
    if (script === "start") runCmd = "npm start"
    else if (script === "build") runCmd = "npm run dev"
    else runCmd = `npm run ${script}`
  }

  const commands: string[] = []
  if (p.project_folder) commands.push(`cd "${p.project_folder}"`)
  commands.push(runCmd)
  return { folder: p.project_folder, commands }
}

export default function MonitorPageWrapper() {
  return (
    <Suspense fallback={<DashboardLayout><div className="p-6 text-muted-foreground">Loading monitor...</div></DashboardLayout>}>
      <MonitorPage />
    </Suspense>
  )
}

function MonitorPage() {
  const searchParams = useSearchParams()
  const focusTask = searchParams.get("task")

  const [pipelines, setPipelines] = useState<Record<string, PipelineStatus>>({})
  const [expandedTask, setExpandedTask] = useState<string | null>(focusTask)
  const [rejectionFeedback, setRejectionFeedback] = useState("")
  const [showRejectModal, setShowRejectModal] = useState<string | null>(null)
  const pollRef = useRef<NodeJS.Timeout | null>(null)
  const [activeTab, setActiveTab] = useState<"plan" | "build" | "check" | "files" | "history" | "todo">("build")
  const [prebuiltDesc, setPrebuiltDesc] = useState("")
  const [issueDesc, setIssueDesc] = useState("")
  const [issueError, setIssueError] = useState("")
  const [showDeployModal, setShowDeployModal] = useState<string | null>(null)
  const [deployForm, setDeployForm] = useState({ apk_path: "", package_name: "", version: "", version_code: "1", release_notes: "", app_name: "", mode: "auto", featured: false, published: false })
  const [copied, setCopied] = useState(false)
  const [zipState, setZipState] = useState<{ taskId: string; busy: boolean; message: string } | null>(null)

  const fetchPipelines = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8001/api/pipelines")
      const data = await res.json()
      let updatedPipelines = data.pipelines || {}
      
      if (focusTask) {
        const detailRes = await fetch(`http://127.0.0.1:8001/api/pipeline/${focusTask}`)
        const detailData = await detailRes.json()
        if (!detailData.error) {
          updatedPipelines = { ...updatedPipelines, [focusTask]: detailData }
        }
      }
      
      setPipelines(updatedPipelines)
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => { fetchPipelines() }, [])
  useEffect(() => {
    pollRef.current = setInterval(fetchPipelines, 2000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [focusTask])

  useEffect(() => {
    if (focusTask) {
      setExpandedTask(focusTask)
      fetch(`http://127.0.0.1:8001/api/pipeline/${focusTask}`)
        .then((r) => r.json())
        .then((data) => {
          if (!data.error) {
            setPipelines((prev) => ({ ...prev, [focusTask]: data }))
          }
        })
        .catch(() => {})
    }
  }, [focusTask])

  const approvePlan = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/approve-plan`, { method: "POST" })
    fetchPipelines()
  }

  const rejectPlan = async (taskId: string) => {
    setShowRejectModal(taskId)
  }

  const submitRejection = async () => {
    if (!showRejectModal) return
    await fetch(`http://127.0.0.1:8001/api/pipeline/${showRejectModal}/reject-plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback: rejectionFeedback }),
    })
    setShowRejectModal(null)
    setRejectionFeedback("")
    fetchPipelines()
  }

  const approveDeploy = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/approve-deploy`, { method: "POST" })
    fetchPipelines()
  }

  const prebuiltAction = async (taskId: string, action: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/prebuilt-action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, description: prebuiltDesc }),
    })
    setPrebuiltDesc("")
    fetchPipelines()
  }

  const copyRun = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {}
  }

  const downloadZip = async (taskId: string) => {
    setZipState({ taskId, busy: true, message: "Creating ZIP on your PC..." })
    try {
      const p = expanded
      const projectId = p?.project_id || ""
      if (!projectId) throw new Error("No project associated with this task")
      const zipRes = await fetch(`http://127.0.0.1:8001/api/projects/${projectId}/zip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      })
      const zipData = await zipRes.json()
      if (zipData.status === "ok" && zipData.result?.path) {
        setZipState({ taskId, busy: false, message: `ZIP saved to: ${zipData.result.path}` })
      } else {
        setZipState({ taskId, busy: false, message: zipData.result?.error || zipData.error || "ZIP failed" })
      }
    } catch (e: any) {
      setZipState({ taskId, busy: false, message: e.message })
    }
  }

  const solveIssues = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/solve-issues`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: prebuiltDesc }),
    })
    setPrebuiltDesc("")
    fetchPipelines()
  }

  const deployToStore = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/deploy-to-store`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(deployForm),
    })
    setShowDeployModal(null)
    setDeployForm({ apk_path: "", package_name: "", version: "", version_code: "1", release_notes: "", app_name: "", mode: "auto", featured: false, published: false })
    fetchPipelines()
  }

  const stopPipeline = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/stop`, { method: "POST" })
    fetchPipelines()
  }

  const submitIssue = async (taskId: string) => {
    if (!issueDesc.trim()) return
    try {
      const res = await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/submit-issue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: issueDesc }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
    } catch (e: any) {
      setIssueError(`Failed to send request: ${e?.message || e}`)
      console.error(e)
      return
    }
    setIssueError("")
    setIssueDesc("")
    fetchPipelines()
  }

  const deleteTask = async (taskId: string) => {
    if (!confirm("Delete this task?")) return
    await fetch(`http://127.0.0.1:8001/api/tasks/${taskId}`, { method: "DELETE" })
    fetchPipelines()
  }

  const restartPipeline = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/restart`, { method: "POST" })
    fetchPipelines()
  }

  const activePipelines = Object.values(pipelines).filter((p) => p.stage !== "idle")
  const completedPipelines = Object.values(pipelines).filter((p) => p.stage === "completed")
  const allPipelines = Object.values(pipelines)

  const expanded = expandedTask ? pipelines[expandedTask] : null

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Build Monitor</h1>
            <p className="text-muted-foreground">
              {activePipelines.length} active | {completedPipelines.length} completed | {allPipelines.length} total
            </p>
          </div>
        </div>

        {allPipelines.length === 0 && (
          <div className="rounded-lg border border-border bg-card p-12 text-center">
            <p className="text-muted-foreground text-lg">No builds yet</p>
            <p className="text-muted-foreground text-sm mt-2">Go to Projects and click "Start Building" on a task</p>
          </div>
        )}

        {allPipelines.length > 0 && (
          <div className="grid grid-cols-12 gap-6">
            {/* Left: Pipeline List */}
            <div className="col-span-4 space-y-2 max-h-[80vh] overflow-y-auto">
              {allPipelines.map((p) => {
                const progress = getProgress(p.stage)
                const isActive = !["completed", "failed", "idle"].includes(p.stage)
                return (
                  <div
                    key={p.task_id}
                    onClick={() => { setExpandedTask(p.task_id); setActiveTab("build"); }}
                    className={`rounded-lg border p-3 cursor-pointer transition-all ${
                      expandedTask === p.task_id
                        ? "border-primary bg-primary/5"
                        : "border-border bg-card hover:bg-secondary/50"
                    }`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-semibold truncate">{p.title || p.task_id}</h4>
                        <p className="text-xs text-muted-foreground truncate">{p.description}</p>
                      </div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ml-2 shrink-0 ${stageColors[p.stage]}`}>
                        {stageIcons[p.stage]} {stageLabels[p.stage]}
                      </span>
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full bg-secondary rounded-full h-1.5 mb-1">
                      <div
                        className={`h-1.5 rounded-full transition-all duration-500 ${
                          p.stage === "completed" ? "bg-green-500" :
                          p.stage === "failed" ? "bg-red-500" :
                          "bg-primary animate-pulse"
                        }`}
                        style={{ width: `${progress}%` }}
                      />
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                      <span>{progress}%</span>
                      {p.current_agent && (
                        <span className="text-blue-400 font-medium">{p.current_agent}</span>
                      )}
                      {p.files_written && p.files_written.length > 0 && (
                        <span>{p.files_written.length} files</span>
                      )}
                      {p.history && p.history.length > 0 && (
                        <span>{p.history.length} steps</span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Right: Detail View */}
            <div className="col-span-8">
              {!expanded && (
                <div className="rounded-lg border border-border bg-card p-12 text-center">
                  <p className="text-muted-foreground">Select a build to view details</p>
                </div>
              )}

              {expanded && (
                <div className="rounded-lg border border-border bg-card overflow-hidden">
                  {/* Header */}
                  <div className={`p-4 border-b border-border ${stageColors[expanded.stage]}`}>
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-semibold">{expanded.title}</h3>
                        <p className="text-xs text-muted-foreground">{expanded.description}</p>
                      </div>
                      <div className="text-right">
                        <span className="text-lg font-bold">{stageIcons[expanded.stage]}</span>
                        <p className="text-xs font-medium">{stageLabels[expanded.stage]}</p>
                      </div>
                    </div>

                    {/* Current Agent Working */}
                    {expanded.current_agent && (
                      <div className="mt-3 rounded-lg border border-blue-500/30 bg-blue-500/10 px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
                          <span className="text-xs font-bold text-blue-300 uppercase">{expanded.current_agent}</span>
                        </div>
                        <p className="mt-1 text-xs text-blue-200">{expanded.current_action}</p>
                      </div>
                    )}

                    {/* Progress Bar */}
                    <div className="w-full bg-black/20 rounded-full h-2 mt-3">
                      <div
                        className={`h-2 rounded-full transition-all duration-700 ${
                          expanded.stage === "completed" ? "bg-green-400" :
                          expanded.stage === "failed" ? "bg-red-400" :
                          "bg-primary animate-pulse"
                        }`}
                        style={{ width: `${getProgress(expanded.stage)}%` }}
                      />
                    </div>

                    {/* How to Run */}
                    {(() => {
                      const run = buildRunInstructions(expanded)
                      if (!run) return null
                      return (
                        <div className="mt-3 rounded-lg border border-green-500/30 bg-green-500/5 px-4 py-3">
                          <div className="flex items-center justify-between mb-2">
                            <h4 className="text-xs font-bold text-green-300 uppercase tracking-wide">
                              ▶ How to Run This Project
                            </h4>
                            <div className="flex items-center gap-2">
                              {expanded.project_folder && (
                                <button
                                  onClick={() => downloadZip(expanded.task_id)}
                                  disabled={zipState?.busy}
                                  className="text-[11px] font-medium px-2 py-1 rounded-md bg-emerald-500/20 hover:bg-emerald-500/30 transition-colors disabled:opacity-50"
                                >
                                  {zipState?.busy ? "Zipping..." : "⬇ Download ZIP"}
                                </button>
                              )}
                              <button
                                onClick={() => copyRun(run.commands.join(" && "))}
                                className="text-[11px] font-medium px-2 py-1 rounded-md bg-white/10 hover:bg-white/20 transition-colors"
                              >
                                {copied ? "✓ Copied" : "Copy"}
                              </button>
                            </div>
                          </div>
                          {zipState && zipState.taskId === expanded.task_id && zipState.message && !zipState.busy && (
                            <p className="text-[11px] text-muted-foreground mb-2">{zipState.message}</p>
                          )}
                          <div className="space-y-1.5">
                            {run.commands.map((cmd, i) => (
                              <div key={i} className="flex items-center gap-2">
                                <span className="text-[10px] text-green-400/70 font-mono">$</span>
                                <code className="text-xs font-mono text-green-100 bg-black/30 rounded px-2 py-1 flex-1 overflow-x-auto whitespace-pre">
                                  {cmd}
                                </code>
                              </div>
                            ))}
                          </div>
                          {run.folder && (
                            <p className="text-[10px] text-muted-foreground mt-2">
                              Run from: <code className="text-green-300">{run.folder}</code>
                            </p>
                          )}
                        </div>
                      )
                    })()}
                  </div>

                  {/* Tabs */}
                  <div className="flex border-b border-border">
                    {(["build", "plan", "check", "todo", "files", "history"] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
                          activeTab === tab
                            ? "border-primary text-primary"
                            : "border-transparent text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {tab === "build" && "Build Output"}
                        {tab === "plan" && "Plan"}
                        {tab === "check" && "Validation"}
                        {tab === "todo" && `Todo (${expanded.todo_list?.filter((t) => t.status !== "fixed").length || 0})`}
                        {tab === "files" && `Files (${expanded.files_written?.length || 0})`}
                        {tab === "history" && `History (${expanded.history?.length || 0})`}
                      </button>
                    ))}
                  </div>

                  {/* Tab Content */}
                  <div className="p-4 max-h-[50vh] overflow-y-auto">
                    {/* Build Output Tab */}
                    {activeTab === "build" && (
                      <div>
                        {expanded.stage === "planning" && (
                          <div className="flex items-center gap-3 p-4 bg-purple-500/10 rounded-lg">
                            <span className="text-purple-400 animate-pulse text-lg">[*]</span>
                            <div>
                              <p className="text-sm font-medium text-purple-400">Planner Agent is working...</p>
                              <p className="text-xs text-muted-foreground">Creating implementation plan for your project</p>
                            </div>
                          </div>
                        )}

                        {expanded.stage === "building" && (
                          <div className="flex items-center gap-3 p-4 bg-blue-500/10 rounded-lg">
                            <span className="text-blue-400 animate-pulse text-lg">[*]</span>
                            <div>
                              <p className="text-sm font-medium text-blue-400">Building Agents are working...</p>
                              <p className="text-xs text-muted-foreground">Frontend and Backend agents are writing code</p>
                            </div>
                          </div>
                        )}

                        {expanded.stage === "checking" && (
                          <div className="flex items-center gap-3 p-4 bg-orange-500/10 rounded-lg">
                            <span className="text-orange-400 animate-pulse text-lg">[?]</span>
                            <div>
                              <p className="text-sm font-medium text-orange-400">Checker Agent is validating...</p>
                              <p className="text-xs text-muted-foreground">Reviewing code quality and completeness</p>
                            </div>
                          </div>
                        )}

                        {expanded.stage === "deploying" && (
                          <div className="flex items-center gap-3 p-4 bg-cyan-500/10 rounded-lg">
                            <span className="text-cyan-400 animate-pulse text-lg">[^]</span>
                            <div>
                              <p className="text-sm font-medium text-cyan-400">Deployment Agent is deploying...</p>
                              <p className="text-xs text-muted-foreground">Setting up and deploying your project</p>
                            </div>
                          </div>
                        )}

                        {expanded.build_output && (
                          <div className="mt-4">
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="text-xs font-semibold text-muted-foreground">Agent Output</h4>
                              <button
                                onClick={() => navigator.clipboard.writeText(expanded.build_output)}
                                className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded hover:bg-secondary"
                              >
                                Copy
                              </button>
                            </div>
                            <div
                              className="rounded-lg bg-secondary p-4 text-xs max-h-[40vh] overflow-y-auto"
                              dangerouslySetInnerHTML={{ __html: formatMd(expanded.build_output.slice(0, 10000)) }}
                            />
                          </div>
                        )}

                        {expanded.stage === "completed" && (
                          <div className="mt-4 p-4 bg-green-500/10 rounded-lg border border-green-500/30">
                            <p className="text-sm font-semibold text-green-400">Build Complete!</p>
                            {expanded.deploy_output && (
                              <div
                                className="mt-2 text-xs"
                                dangerouslySetInnerHTML={{ __html: formatMd(expanded.deploy_output.slice(0, 5000)) }}
                              />
                            )}
                          </div>
                        )}

                        {expanded.stage === "failed" && (
                          <div className="mt-4 p-4 bg-red-500/10 rounded-lg border border-red-500/30 space-y-3">
                            <div className="flex items-center justify-between">
                              <p className="text-sm font-bold text-red-400">❌ Pipeline Failed / Stopped</p>
                            </div>
                            <p className="text-xs text-red-300 font-mono bg-background/50 p-2 rounded border border-red-500/20">{expanded.error}</p>
                            <button onClick={() => restartPipeline(expanded.task_id)}
                              className="rounded-lg bg-amber-600 px-4 py-2 text-xs font-semibold text-white hover:bg-amber-700 shadow-sm transition-colors">
                              🔄 Try Again (Restart from Layer 1 Planning)
                            </button>
                          </div>
                        )}

                        {expanded.error && expanded.stage !== "failed" && (
                          <div className="mt-4 p-3 bg-red-500/10 rounded-lg border border-red-500/30">
                            <p className="text-xs text-red-400">{expanded.error}</p>
                          </div>
                        )}

                        {/* Ask the Agent - always available so the user can add/remove/change anything */}
                        <div className="mt-4 space-y-3 rounded-lg border border-border bg-secondary/30 p-4">
                          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Ask the Agent (Add / Remove / Change)</label>
                          <div className="flex flex-wrap gap-1.5 py-1">
                            {[
                              "➕ Add a new page / feature",
                              "➖ Remove a page / feature",
                              "✏️ Change / update existing code",
                              "🛠️ Fix build and runtime errors",
                              "🎨 Fix responsive UI styling & components",
                              "⚡ Fix API routes and data fetching",
                            ].map((promptText, i) => (
                              <button
                                key={i}
                                type="button"
                                onClick={() => setIssueDesc(promptText)}
                                className="text-[11px] bg-background hover:bg-secondary border border-border px-2.5 py-1 rounded-full text-foreground/80 hover:text-foreground transition-colors"
                              >
                                {promptText}
                              </button>
                            ))}
                          </div>
                          <textarea
                            value={issueDesc}
                            onChange={(e) => setIssueDesc(e.target.value)}
                            placeholder="e.g. Add a login page, Remove the settings section, Change the button colors to blue..."
                            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-20 resize-none"
                          />
                          <div className="flex gap-2">
                            <button onClick={() => submitIssue(expanded.task_id)}
                              disabled={!issueDesc.trim()}
                              className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-40 disabled:cursor-not-allowed">
                              Ask Agent
                            </button>
                            {["building", "planning", "checking", "deploying", "fixing"].includes(expanded.stage) && (
                              <button onClick={() => stopPipeline(expanded.task_id)}
                                className="rounded-lg bg-red-600/20 text-red-400 px-4 py-2 text-sm font-medium hover:bg-red-600/30 border border-red-500/30">
                                Stop Build
                              </button>
                            )}
                            <button onClick={() => deleteTask(expanded.task_id)}
                              className="rounded-lg bg-red-600/10 text-red-400 px-4 py-2 text-sm font-medium hover:bg-red-600/20 border border-red-500/20">
                              Delete
                            </button>
                          </div>
                          {issueError && (
                            <p className="mt-2 text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded p-2">{issueError}</p>
                          )}
                        </div>

                        {/* Restart button for failed/completed prebuilt builds */}
                        {["failed", "completed", "awaiting_prebuilt_action"].includes(expanded.stage) && expanded.project_mode === "prebuilt" && (
                          <div className="mt-4">
                            <button onClick={() => restartPipeline(expanded.task_id)}
                              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                              Restart Pipeline
                            </button>
                          </div>
                        )}

                        {expanded.stage === "awaiting_plan_approval" && expanded.plan_content && (
                          <div className="mt-4 space-y-3">
                            <div className="rounded-lg bg-secondary p-4 text-xs" dangerouslySetInnerHTML={{ __html: formatMd(expanded.plan_content.slice(0, 5000)) }} />
                            <div className="flex gap-2">
                              <button onClick={() => approvePlan(expanded.task_id)}
                                className="rounded-lg bg-green-600 px-6 py-2 text-sm font-medium text-white hover:bg-green-700">
                                Approve Plan
                              </button>
                              <button onClick={() => rejectPlan(expanded.task_id)}
                                className="rounded-lg bg-red-600 px-6 py-2 text-sm font-medium text-white hover:bg-red-700">
                                Reject and Redo
                              </button>
                            </div>
                          </div>
                        )}

                        {expanded.stage === "awaiting_check_approval" && (
                          <div className="mt-4 space-y-3">
                            {expanded.check_output && (
                              <div className="rounded-lg bg-secondary p-4 text-xs" dangerouslySetInnerHTML={{ __html: formatMd(expanded.check_output.slice(0, 5000)) }} />
                            )}
                            <button onClick={() => approveDeploy(expanded.task_id)}
                              className="rounded-lg bg-cyan-600 px-6 py-2 text-sm font-medium text-white hover:bg-cyan-700">
                              Deploy Now
                            </button>
                          </div>
                        )}

                        {expanded.stage === "awaiting_prebuilt_action" && (
                          <div className="mt-4 space-y-3">
                            {expanded.check_output && (
                              <div className="rounded-lg bg-secondary p-4 text-xs" dangerouslySetInnerHTML={{ __html: formatMd(expanded.check_output.slice(0, 5000)) }} />
                            )}
                            <textarea
                              value={prebuiltDesc}
                              onChange={(e) => setPrebuiltDesc(e.target.value)}
                              placeholder="Optional: Describe specific issues, changes, or what you want the agent to focus on..."
                              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-20 resize-none"
                            />
                            <div className="flex flex-wrap gap-2">
                              <button onClick={() => prebuiltAction(expanded.task_id, "analyze")}
                                className="rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700">
                                Analyze Issues
                              </button>
                              <button onClick={() => prebuiltAction(expanded.task_id, "complete")}
                                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                                Complete Project
                              </button>
                              <button onClick={() => prebuiltAction(expanded.task_id, "deploy")}
                                className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700">
                                Deploy (Docker)
                              </button>
                              <button onClick={() => { setShowDeployModal(expanded.task_id); setDeployForm({ ...deployForm, package_name: expanded.project_name || "", app_name: expanded.title || "" }) }}
                                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
                                Deploy to Store
                              </button>
                              <button onClick={() => prebuiltAction(expanded.task_id, "run")}
                                className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700">
                                How to Run
                              </button>
                              {expanded.check_output && expanded.check_output.toLowerCase().includes("issue") && (
                                <button onClick={() => solveIssues(expanded.task_id)}
                                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700">
                                  Solve Issues
                                </button>
                              )}
                            </div>
                          </div>
                        )}

                        {!expanded.build_output && !expanded.plan_content && !["completed", "failed"].includes(expanded.stage) && (
                          <p className="text-xs text-muted-foreground text-center py-4">
                            Waiting for agent response...
                          </p>
                        )}
                      </div>
                    )}

                    {/* Plan Tab */}
                    {activeTab === "plan" && (
                      <div>
                        {expanded.plan_content ? (
                          <div className="rounded-lg bg-secondary p-4 text-xs" dangerouslySetInnerHTML={{ __html: formatMd(expanded.plan_content) }} />
                        ) : (
                          <p className="text-xs text-muted-foreground text-center py-4">No plan yet</p>
                        )}
                      </div>
                    )}

                    {/* Check Tab */}
                    {activeTab === "check" && (
                      <div>
                        {expanded.check_output ? (
                          <div className="rounded-lg bg-secondary p-4 text-xs" dangerouslySetInnerHTML={{ __html: formatMd(expanded.check_output) }} />
                        ) : (
                          <p className="text-xs text-muted-foreground text-center py-4">No validation output yet</p>
                        )}
                      </div>
                    )}

                    {/* Todo Tab */}
                    {activeTab === "todo" && (
                      <div>
                        {expanded.todo_list && expanded.todo_list.length > 0 ? (
                          <div className="space-y-2">
                            <div className="flex items-center justify-between mb-3">
                              <span className="text-xs font-semibold text-muted-foreground">
                                {expanded.todo_list.filter((t) => t.status === "fixed").length} / {expanded.todo_list.length} fixed
                              </span>
                              <div className="w-32 bg-secondary rounded-full h-1.5">
                                <div
                                  className="h-1.5 rounded-full bg-green-500 transition-all duration-500"
                                  style={{ width: `${Math.round((expanded.todo_list.filter((t) => t.status === "fixed").length / expanded.todo_list.length) * 100)}%` }}
                                />
                              </div>
                            </div>
                            {expanded.todo_list.map((item) => (
                              <div key={item.id} className={`rounded-lg border p-3 ${
                                item.status === "fixed"
                                  ? "border-green-500/30 bg-green-500/5"
                                  : "border-amber-500/30 bg-amber-500/5"
                              }`}>
                                <div className="flex items-start gap-2">
                                  <span className={`mt-0.5 text-xs font-bold ${
                                    item.status === "fixed" ? "text-green-400" : "text-amber-400"
                                  }`}>
                                    {item.status === "fixed" ? "[OK]" : "[ ]"}
                                  </span>
                                  <div className="flex-1 min-w-0">
                                    <p className={`text-xs ${item.status === "fixed" ? "text-green-300 line-through opacity-60" : ""}`}>
                                      {item.description}
                                    </p>
                                    {item.source && (
                                      <p className="text-[10px] text-muted-foreground mt-1">
                                        Found by: {item.source}
                                      </p>
                                    )}
                                    {item.details && (
                                      <p className="text-[10px] text-muted-foreground mt-1 whitespace-pre-wrap">{item.details}</p>
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-muted-foreground text-center py-4">No todo items yet</p>
                        )}
                      </div>
                    )}

                    {/* Files Tab */}
                    {activeTab === "files" && (
                      <div>
                        {expanded.files_written && expanded.files_written.length > 0 ? (
                          <div className="space-y-1">
                            {expanded.files_written.map((f, i) => (
                              <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-green-500/5 border border-green-500/20">
                                <span className="text-xs text-green-400 font-mono">{f.path}</span>
                                <span className="text-[10px] text-muted-foreground">{f.size} bytes</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-muted-foreground text-center py-4">No files written yet</p>
                        )}

                        {expanded.commands_run && expanded.commands_run.length > 0 && (
                          <div className="mt-4 space-y-1">
                            <h4 className="text-xs font-semibold text-muted-foreground mb-2">Commands Executed</h4>
                            {expanded.commands_run.map((c, i) => (
                              <div key={i} className="rounded-lg bg-secondary p-2">
                                <p className="text-xs font-mono text-cyan-400">$ {c.command}</p>
                                {c.stdout && <p className="text-[10px] text-muted-foreground mt-1 max-h-20 overflow-y-auto">{c.stdout.slice(0, 500)}</p>}
                                {c.stderr && <p className="text-[10px] text-red-400 mt-1">{c.stderr.slice(0, 200)}</p>}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* History Tab */}
                    {activeTab === "history" && (
                      <div>
                        {expanded.history && expanded.history.length > 0 ? (
                          <div className="space-y-2">
                            {expanded.history.map((h, i) => (
                              <div key={i}>
                                {h.stage === "helper_consult" ? (
                                  <div className="rounded-lg border border-purple-500/30 bg-purple-500/5 p-3">
                                    <div className="flex items-center gap-2 mb-1.5">
                                      <span className="text-xs font-bold text-purple-400">Helper Guidance</span>
                                      <span className="text-[10px] text-muted-foreground">{formatTime(h.timestamp)}</span>
                                    </div>
                                    <div className="text-xs text-foreground whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: formatMd(h.message.replace(/^Helper guidance \(attempt \d+\):\s*/, "")) }} />
                                  </div>
                                ) : (
                                  <div className="flex gap-3 items-start">
                                    <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${
                                      h.stage === "failed" ? "bg-red-500" :
                                      h.stage === "completed" ? "bg-green-500" :
                                      "bg-primary"
                                    }`} />
                                    <div className="flex-1 min-w-0">
                                      <p className="text-xs">{h.message}</p>
                                      <div className="flex items-center gap-2 mt-0.5">
                                        <span className="text-[10px] text-muted-foreground">{formatTime(h.timestamp)}</span>
                                        <span className={`text-[10px] px-1 py-0 rounded ${
                                          h.stage === "failed" ? "bg-red-500/10 text-red-400" :
                                          h.stage === "completed" ? "bg-green-500/10 text-green-400" :
                                          "bg-secondary text-muted-foreground"
                                        }`}>{h.stage}</span>
                                      </div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-muted-foreground text-center py-4">No history yet</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Rejection Modal */}
        {showRejectModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="rounded-xl border border-border bg-card p-6 w-full max-w-md space-y-4">
              <h3 className="font-semibold">Reject Plan -- Feedback</h3>
              <textarea value={rejectionFeedback} onChange={(e) => setRejectionFeedback(e.target.value)}
                placeholder="What needs to change? The agent will re-plan based on your feedback..."
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-24 resize-none" />
              <div className="flex gap-2 justify-end">
                <button onClick={() => { setShowRejectModal(null); setRejectionFeedback(""); }}
                  className="rounded-lg bg-secondary px-4 py-2 text-sm">Cancel</button>
                <button onClick={submitRejection}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700">
                  Reject and Redo
                </button>
              </div>
            </div>
          </div>
        )}

        {showDeployModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="rounded-xl border border-border bg-card p-6 w-full max-w-lg space-y-4 max-h-[90vh] overflow-y-auto">
              <h3 className="font-semibold text-emerald-400">Deploy to BritStore</h3>

              <div className="flex gap-2">
                <button onClick={() => setDeployForm({ ...deployForm, mode: "auto" })}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium border ${deployForm.mode === "auto" ? "bg-emerald-600 text-white border-emerald-500" : "bg-secondary text-muted-foreground border-border"}`}>
                  Auto Detect
                </button>
                <button onClick={() => setDeployForm({ ...deployForm, mode: "update" })}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium border ${deployForm.mode === "update" ? "bg-blue-600 text-white border-blue-500" : "bg-secondary text-muted-foreground border-border"}`}>
                  Update Existing
                </button>
                <button onClick={() => setDeployForm({ ...deployForm, mode: "new" })}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium border ${deployForm.mode === "new" ? "bg-purple-600 text-white border-purple-500" : "bg-secondary text-muted-foreground border-border"}`}>
                  New App
                </button>
              </div>

              <div className="text-xs text-muted-foreground bg-secondary/50 rounded-lg p-3">
                {deployForm.mode === "auto" && "Checks store: if package exists it updates, if not it creates a new app with AI-generated content."}
                {deployForm.mode === "update" && "Uploads new version to an existing app. Package must already exist in store."}
                {deployForm.mode === "new" && "Creates a new store listing. Agent generates name, descriptions, release notes. You add icon + screenshots via store dashboard after."}
              </div>

              <div className="space-y-3">
                <div>
                  <label className="text-xs text-muted-foreground">APK File Path *</label>
                  <input value={deployForm.apk_path} onChange={(e) => setDeployForm({ ...deployForm, apk_path: e.target.value })}
                    placeholder="D:\path\to\app.apk"
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                </div>

                {deployForm.mode !== "new" && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground">Package Name *</label>
                      <input value={deployForm.package_name} onChange={(e) => setDeployForm({ ...deployForm, package_name: e.target.value })}
                        placeholder="com.britsync.myapp"
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Version *</label>
                      <input value={deployForm.version} onChange={(e) => setDeployForm({ ...deployForm, version: e.target.value })}
                        placeholder="1.0.0"
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Version Code *</label>
                      <input value={deployForm.version_code} onChange={(e) => setDeployForm({ ...deployForm, version_code: e.target.value })}
                        placeholder="1" type="number"
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">App Name</label>
                      <input value={deployForm.app_name} onChange={(e) => setDeployForm({ ...deployForm, app_name: e.target.value })}
                        placeholder="My App"
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                    </div>
                  </div>
                )}

                {deployForm.mode === "new" && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground">Package Name (optional)</label>
                      <input value={deployForm.package_name} onChange={(e) => setDeployForm({ ...deployForm, package_name: e.target.value })}
                        placeholder="Auto-detect from APK"
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Version</label>
                      <input value={deployForm.version} onChange={(e) => setDeployForm({ ...deployForm, version: e.target.value })}
                        placeholder="Auto-detect from APK"
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                    </div>
                  </div>
                )}

                <div>
                  <label className="text-xs text-muted-foreground">Release Notes</label>
                  <textarea value={deployForm.release_notes} onChange={(e) => setDeployForm({ ...deployForm, release_notes: e.target.value })}
                    placeholder={deployForm.mode === "new" ? "Auto-generated by agent if empty" : "What's new in this version..."}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-20 resize-none" />
                </div>

                <div className="flex gap-6">
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={deployForm.published} onChange={(e) => setDeployForm({ ...deployForm, published: e.target.checked })}
                      className="rounded border-border" />
                    <span className="text-muted-foreground">Published</span>
                  </label>
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={deployForm.featured} onChange={(e) => setDeployForm({ ...deployForm, featured: e.target.checked })}
                      className="rounded border-border" />
                    <span className="text-muted-foreground">Featured</span>
                  </label>
                </div>
              </div>

              <div className="flex gap-2 justify-end">
                <button onClick={() => setShowDeployModal(null)}
                  className="rounded-lg bg-secondary px-4 py-2 text-sm">Cancel</button>
                <button onClick={() => deployToStore(showDeployModal)}
                  disabled={!deployForm.apk_path}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                  Deploy to Store
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
