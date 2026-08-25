"use client"

import { useEffect, useState, useRef } from "react"
import { useRouter } from "next/navigation"
import { DashboardLayout } from "@/components/layout/dashboard-layout"

interface Task {
  id: string
  title: string
  description: string
  status: string
  priority: string
  assigned_to: string | null
  project_id: string | null
  task_mode?: string
}

interface TestIssue {
  severity: string
  area: string
  title: string
  detail: string
}

interface TestReport {
  passed: boolean
  summary: string
  issues: TestIssue[]
  checked_at?: string
  raw?: {
    install_output?: string
    run_output?: string
    browser_check?: string
    errors?: string[]
  }
}

interface PipelineStatus {
  task_id: string
  stage: string
  error: string
  current_agent: string
  current_action: string
  history: { stage: string; message: string; timestamp: string }[]
  task_mode?: string
  test_report?: TestReport
  check_output?: string
}

interface Project {
  id: string
  name: string
  folder: string
}

const stageColors: Record<string, string> = {
  idle: "bg-gray-500/10 text-gray-400",
  testing: "bg-emerald-500/10 text-emerald-400 animate-pulse",
  test_failed: "bg-rose-500/10 text-rose-400",
  fixing: "bg-blue-500/10 text-blue-400 animate-pulse",
  completed: "bg-green-500/10 text-green-400",
  failed: "bg-red-500/10 text-red-400",
  checking: "bg-orange-500/10 text-orange-400 animate-pulse",
  building: "bg-blue-500/10 text-blue-400 animate-pulse",
}

const stageLabels: Record<string, string> = {
  idle: "Ready",
  testing: "Testing...",
  test_failed: "Issues Found",
  fixing: "Dev Team Fixing...",
  completed: "Tests Passed",
  failed: "Failed",
  checking: "Validating...",
  building: "Building...",
}

export default function TesterPage() {
  const router = useRouter()
  const [tasks, setTasks] = useState<Task[]>([])
  const [pipelineTasks, setPipelineTasks] = useState<Record<string, PipelineStatus>>({})
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState("")
  const [newTask, setNewTask] = useState({ title: "", description: "", priority: "medium", project_id: "" })
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  const fetchData = () => {
    Promise.all([
      fetch("http://127.0.0.1:8001/api/tasks?task_mode=tester").then((r) => r.json()),
      fetch("http://127.0.0.1:8001/api/pipelines").then((r) => r.json()),
      fetch("http://127.0.0.1:8001/api/projects").then((r) => r.json()),
    ])
      .then(([taskData, pipeData, projData]) => {
        setTasks(taskData.tasks || [])
        if (pipeData.pipelines) setPipelineTasks(pipeData.pipelines)
        setProjects(projData.projects || [])
        setError("")
        setLoading(false)
      })
      .catch(() => {
        setError("Could not connect to API at http://127.0.0.1:8001")
        setLoading(false)
      })
  }

  useEffect(() => { fetchData() }, [])
  useEffect(() => {
    pollRef.current = setInterval(fetchData, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const createTask = async () => {
    if (!newTask.title) return
    setCreating(true)
    setError("")
    try {
      const res = await fetch("http://127.0.0.1:8001/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newTask.title,
          description: newTask.description,
          priority: newTask.priority,
          project_id: newTask.project_id || null,
          task_mode: "tester",
        }),
      })
      if (res.ok) {
        setNewTask({ title: "", description: "", priority: "medium", project_id: "" })
        setShowCreate(false)
        fetchData()
      } else {
        const data = await res.json()
        setError(data.detail || "Failed to create task")
      }
    } catch (e: any) {
      setError(e.message)
    }
    setCreating(false)
  }

  const postAction = async (url: string) => {
    setError("")
    try {
      const res = await fetch(url, { method: "POST" })
      let data: any = null
      try { data = await res.json() } catch { /* ignore */ }
      if (!res.ok) {
        setError(data?.detail || data?.error || `Request failed (HTTP ${res.status})`)
        return
      }
      if (data?.error) { setError(data.error); return }
      fetchData()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const startTesting = (taskId: string) => postAction(`http://127.0.0.1:8001/api/pipeline/${taskId}/start-testing`)

  const fixWithDevTeam = (taskId: string) => postAction(`http://127.0.0.1:8001/api/pipeline/${taskId}/fix-with-dev-team`)

  const stopPipeline = (taskId: string) => postAction(`http://127.0.0.1:8001/api/pipeline/${taskId}/stop`)

  const runningStages = ["testing", "fixing", "building", "checking"]

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Tester</h1>
            <p className="text-muted-foreground">
              {tasks.length} test task{tasks.length === 1 ? "" : "s"} - the Tester Agent only tests & reports, it never fixes code
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => { setShowCreate(!showCreate); setError("") }}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
              + New Test Task
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400">{error}</div>
        )}

        {showCreate && (
          <div className="rounded-lg border border-emerald-500/30 bg-card p-6 space-y-4">
            <h3 className="font-semibold">New Test Task</h3>
            <input placeholder="Test task title (e.g., Test the landing page & auth flow)" value={newTask.title}
              onChange={(e) => setNewTask({ ...newTask, title: e.target.value })}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
            <textarea placeholder="What to check... (e.g., login flow, checkout, mobile view)" value={newTask.description}
              onChange={(e) => setNewTask({ ...newTask, description: e.target.value })}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-20 resize-none" />
            <div className="flex gap-4">
              <select value={newTask.project_id} onChange={(e) => setNewTask({ ...newTask, project_id: e.target.value })}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm flex-1">
                <option value="">No project (standalone)</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <select value={newTask.priority} onChange={(e) => setNewTask({ ...newTask, priority: e.target.value })}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCreate(false)} className="rounded-lg bg-secondary px-4 py-2 text-sm">Cancel</button>
              <button onClick={createTask} disabled={creating || !newTask.title}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {creating ? "Creating..." : "Create Test Task"}
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : tasks.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-10 text-center">
            <p className="text-sm text-muted-foreground">No test tasks yet. Create one above or make a Tester-mode task from the Projects page.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => {
              const pipeline = pipelineTasks[task.id]
              const stage = pipeline?.stage || "idle"
              const report = pipeline?.test_report
              const project = projects.find((p) => p.id === task.project_id)
              const hasFolder = !!project?.folder
              return (
                <div key={task.id} className="rounded-lg border border-border bg-card p-4 space-y-3">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h4 className="font-semibold text-sm">{task.title}</h4>
                      {task.description && <p className="text-xs text-muted-foreground mt-1">{task.description}</p>}
                      <p className="text-xs text-muted-foreground mt-1">
                        {project ? `Project: ${project.name}` : "No project (standalone)"}
                        {project?.folder && <span className="text-green-400 font-mono"> - {project.folder}</span>}
                      </p>
                      {!hasFolder && (
                        <p className="text-xs text-amber-400 mt-1">
                          ⚠ No project folder set. Open the project on the Projects page and set a folder before testing.
                        </p>
                      )}
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${stageColors[stage]}`}>
                      {stageLabels[stage] || stage}
                    </span>
                  </div>

                  {pipeline?.current_agent && runningStages.includes(stage) && (
                    <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2">
                      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                      <span className="text-xs font-bold text-emerald-300 uppercase">{pipeline.current_agent}</span>
                      <span className="text-xs text-emerald-200">{pipeline.current_action}</span>
                    </div>
                  )}

                  {stage === "idle" && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <button onClick={() => startTesting(task.id)}
                        className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 shadow-sm">
                        🧪 Start Testing
                      </button>
                      <button onClick={() => router.push(`/monitor?task=${task.id}`)}
                        className="text-xs text-primary hover:underline font-medium">
                        Open in Monitor
                      </button>
                    </div>
                  )}

                  {stage === "testing" && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs text-emerald-400">Tester Agent is checking the project - it will not change or fix anything...</span>
                      <button onClick={() => stopPipeline(task.id)}
                        className="text-xs bg-red-600/20 text-red-400 px-2 py-0.5 rounded hover:bg-red-600/30">
                        Stop Testing
                      </button>
                    </div>
                  )}

                  {stage === "test_failed" && report && (
                    <div className="space-y-3 border-t border-border pt-3">
                      <div className="rounded-lg border border-rose-500/40 bg-rose-500/5 p-4">
                        <p className="flex items-center gap-2 text-sm font-semibold text-rose-400">
                          <span>⚠</span> {report.summary || "Issues found"}
                        </p>
                        <div className="mt-2 space-y-2">
                          {(report.issues || []).map((issue, idx) => (
                            <div key={idx} className={`rounded-lg border p-2.5 ${issue.severity === "error" ? "border-rose-500/40 bg-rose-500/10" : "border-amber-500/40 bg-amber-500/10"}`}>
                              <p className="text-xs font-semibold">
                                <span className={`uppercase text-[10px] mr-1.5 ${issue.severity === "error" ? "text-rose-400" : "text-amber-400"}`}>
                                  [{issue.severity}] {issue.area}
                                </span>
                                {issue.title}
                              </p>
                              {issue.detail && <p className="text-xs text-muted-foreground mt-1 font-mono break-words">{issue.detail}</p>}
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <button onClick={() => fixWithDevTeam(task.id)}
                          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 shadow-sm">
                          🔧 Fix with Development Team
                        </button>
                        <button onClick={() => startTesting(task.id)}
                          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
                          ↻ Run Tests Again
                        </button>
                        <button onClick={() => router.push(`/monitor?task=${task.id}`)}
                          className="text-xs text-primary hover:underline font-medium">
                          Open in Monitor
                        </button>
                      </div>
                    </div>
                  )}

                  {stage === "completed" && report?.passed && (
                    <div className="space-y-3 border-t border-border pt-3">
                      <div className="rounded-lg border border-green-500/40 bg-green-500/5 p-4">
                        <p className="flex items-center gap-2 text-sm font-semibold text-green-400">
                          <span>✔</span> All tests passed - the project looks good.
                        </p>
                        {report.checked_at && <p className="text-xs text-muted-foreground mt-1">Checked at {new Date(report.checked_at).toLocaleString()}</p>}
                        {report.raw?.browser_check === "ok" && (
                          <p className="text-xs text-green-400 mt-1">Browser check: OK (no console errors)</p>
                        )}
                        {report.raw?.browser_check?.startsWith("skipped") && (
                          <p className="text-xs text-amber-400 mt-1">Browser check: {report.raw.browser_check}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <button onClick={() => startTesting(task.id)}
                          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
                          ↻ Run Tests Again
                        </button>
                        <button onClick={() => router.push(`/monitor?task=${task.id}`)}
                          className="text-xs text-primary hover:underline font-medium">
                          Open in Monitor
                        </button>
                      </div>
                    </div>
                  )}

                  {stage === "fixing" && (
                    <div className="space-y-2 border-t border-border pt-3">
                      <p className="text-xs text-blue-300">
                        Development Team is fixing the tester-reported issues...
                      </p>
                      <div className="flex items-center gap-2 flex-wrap">
                        <button onClick={() => router.push(`/monitor?task=${task.id}`)}
                          className="text-xs text-primary hover:underline font-medium">
                          Watch progress in Monitor
                        </button>
                        <button onClick={() => stopPipeline(task.id)}
                          className="text-xs bg-red-600/20 text-red-400 px-2 py-0.5 rounded hover:bg-red-600/30">
                          Stop
                        </button>
                      </div>
                    </div>
                  )}

                  {stage === "failed" && (
                    <div className="space-y-2 border-t border-border pt-3">
                      <p className="text-xs text-red-400">Pipeline failed: {pipeline?.error || "unknown error"}</p>
                      <div className="flex items-center gap-2 flex-wrap">
                        <button onClick={() => startTesting(task.id)}
                          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
                          ↻ Run Tests Again
                        </button>
                        <button onClick={() => fixWithDevTeam(task.id)}
                          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                          🔧 Fix with Development Team
                        </button>
                      </div>
                    </div>
                  )}

                  {report?.raw && (stage === "test_failed" || stage === "completed") && (
                    <details className="rounded-lg border border-border bg-secondary/30 p-3">
                      <summary className="text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer">Raw check output</summary>
                      <div className="mt-2 space-y-2 text-xs">
                        {report.raw.browser_check && <p className="text-muted-foreground">Browser: {report.raw.browser_check}</p>}
                        {report.raw.errors && report.raw.errors.length > 0 && (
                          <pre className="rounded bg-muted text-red-300 p-2 text-[11px] overflow-x-auto max-h-40">{report.raw.errors.join("\n")}</pre>
                        )}
                        {report.raw.install_output && (
                          <details>
                            <summary className="text-muted-foreground cursor-pointer">Install output</summary>
                            <pre className="rounded bg-muted text-green-400 p-2 text-[11px] overflow-x-auto max-h-40 mt-1">{report.raw.install_output}</pre>
                          </details>
                        )}
                        {report.raw.run_output && (
                          <details>
                            <summary className="text-muted-foreground cursor-pointer">Run output</summary>
                            <pre className="rounded bg-muted text-green-400 p-2 text-[11px] overflow-x-auto max-h-40 mt-1">{report.raw.run_output}</pre>
                          </details>
                        )}
                      </div>
                    </details>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
