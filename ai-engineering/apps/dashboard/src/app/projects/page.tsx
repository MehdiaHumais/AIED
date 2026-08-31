"use client"

import { useEffect, useState, useRef } from "react"
import { useRouter } from "next/navigation"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { useAuth } from "@/components/auth-provider"
import { Monitor } from "lucide-react"

interface Project {
  id: string
  name: string
  codename: string
  description: string
  status: string
  tech_stack: string[]
  tasks_count: number
  mode: string
  folder: string
  created_at: string
}

interface Task {
  id: string
  title: string
  description: string
  status: string
  priority: string
  assigned_to: string | null
  project_id: string | null
  result: string | null
  error: string | null
  task_mode?: string
}

interface PipelineStatus {
  task_id: string
  stage: string
  plan_content: string
  build_output: string
  check_output: string
  error: string
  files_written: { path: string; size: number }[]
  commands_run: { command: string; stdout: string; stderr: string; returncode: number }[]
  history: { stage: string; message: string; timestamp: string }[]
  project_mode: string
  prebuilt_action: string
  current_agent: string
  current_action: string
  todo_list: { id: number; description: string; details: string; source: string; status: string }[]
  analysis_report: string
  rejection_count?: number
}

interface Notification {
  title: string
  message: string
  task_id: string
  type: string
  read: boolean
  timestamp: string
}

const stageColors: Record<string, string> = {
  idle: "bg-gray-500/10 text-gray-400",
  planning: "bg-purple-500/10 text-purple-400 animate-pulse",
  awaiting_plan_approval: "bg-yellow-500/10 text-yellow-400",
  building: "bg-blue-500/10 text-blue-400 animate-pulse",
  checking: "bg-orange-500/10 text-orange-400 animate-pulse",
  awaiting_check_approval: "bg-yellow-500/10 text-yellow-400",
  deploying: "bg-cyan-500/10 text-cyan-400 animate-pulse",
  completed: "bg-green-500/10 text-green-400",
  failed: "bg-red-500/10 text-red-400",
  awaiting_prebuilt_action: "bg-yellow-500/10 text-yellow-400",
  analyzing: "bg-orange-500/10 text-orange-400 animate-pulse",
  fixing: "bg-blue-500/10 text-blue-400 animate-pulse",
  testing: "bg-emerald-500/10 text-emerald-400 animate-pulse",
  test_failed: "bg-rose-500/10 text-rose-400",
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

export default function ProjectsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateProject, setShowCreateProject] = useState(false)
  const [showCreateTask, setShowCreateTask] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState("")
  const [pipelineTasks, setPipelineTasks] = useState<Record<string, PipelineStatus>>({})
  const [filterProject, setFilterProject] = useState("")
  const [expandedTask, setExpandedTask] = useState<string | null>(null)
  const [rejectionFeedback, setRejectionFeedback] = useState("")
  const [showRejectModal, setShowRejectModal] = useState<string | null>(null)
  const pollRef = useRef<NodeJS.Timeout | null>(null)
  const pollBusyRef = useRef(false)
  const formOpenRef = useRef(false)
  const [editProject, setEditProject] = useState<Project | null>(null)
  const [editTask, setEditTask] = useState<Task | null>(null)
  const [editName, setEditName] = useState("")
  const [editDesc, setEditDesc] = useState("")
  const [editCodename, setEditCodename] = useState("")
  const [editPriority, setEditPriority] = useState("medium")
  const [prebuiltDesc, setPrebuiltDesc] = useState("")
  const [agentConnected, setAgentConnected] = useState(false)
  const [agentFolder, setAgentFolder] = useState("")

  const [newProject, setNewProject] = useState({ name: "", codename: "", description: "", tech_stack: "", folder: "", mode: "scratch" })
  const [newTask, setNewTask] = useState({ title: "", description: "", priority: "medium", project_id: "", task_mode: "developer" })

  const fetchData = () => {
    const uid = user?.id ? `?user_id=${user.id}` : ""
    Promise.all([
      fetch(`http://127.0.0.1:8001/api/projects${uid}`).then((r) => r.json()),
      fetch("http://127.0.0.1:8001/api/tasks").then((r) => r.json()),
      fetch("http://127.0.0.1:8001/api/pipelines").then((r) => r.json()),
    ])
      .then(([projData, taskData, pipeData]) => {
        setProjects(projData.projects || [])
        setTasks(taskData.tasks || [])
        if (pipeData.pipelines) {
          setPipelineTasks(pipeData.pipelines)
        }
        setError("")
        setLoading(false)
      })
      .catch(() => {
        setError("Could not connect to API at http://127.0.0.1:8001")
        setLoading(false)
      })
  }

  const pollAll = () => {
    // Never overlap cycles, and stop re-rendering the page while the user is
    // typing in a create/edit form (otherwise fast polls can swallow input
    // focus and keystrokes in the Electron renderer).
    if (pollBusyRef.current || formOpenRef.current || document.hidden) return
    pollBusyRef.current = true
    const uid = user?.id || ""
    Promise.all([
      fetch("http://127.0.0.1:8001/api/tasks")
        .then((r) => r.json())
        .catch(() => null),
      fetch("http://127.0.0.1:8001/api/pipelines")
        .then((r) => r.json())
        .catch(() => null),
      fetch(`http://127.0.0.1:8001/api/agent/status?user_id=${uid}`)
        .then((r) => r.json())
        .catch(() => null),
    ])
      .then(([taskData, pipeData, agentData]) => {
        if (taskData?.tasks) {
          setTasks(taskData.tasks)
        }
        if (pipeData?.pipelines) {
          setPipelineTasks(pipeData.pipelines)
        }
        if (agentData) {
          setAgentConnected(agentData.connected || false)
          setAgentFolder(agentData.project_folder || "")
        }
      })
      .catch(() => {})
      .finally(() => { pollBusyRef.current = false })
  }

  useEffect(() => { if (user) fetchData() }, [user?.id])

  useEffect(() => {
    if (!user) return
    pollRef.current = setInterval(pollAll, 8000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [user?.id])

  const pickFolder = async (setTarget: (path: string) => void) => {
    try {
      const qs = user?.id ? `?user_id=${user.id}` : ""
      const res = await fetch(`http://127.0.0.1:8001/api/agent/select-folder${qs}`)
      const data = await res.json()
      if (data.path) setTarget(data.path)
      else if (data.error) setError(data.error)
    } catch (e: any) {
      setError(e.message)
    }
  }

  const createProject = async () => {
    if (!newProject.name || !newProject.codename) return
    if (newProject.mode === "prebuilt" && !newProject.folder) {
      setError("Prebuilt mode requires a project folder. Please browse and select your existing project folder.")
      return
    }
    setCreating(true)
    setError("")
    try {
      const res = await fetch("http://127.0.0.1:8001/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newProject.name,
          codename: newProject.codename,
          description: newProject.description,
          tech_stack: newProject.tech_stack.split(",").map((s) => s.trim()).filter(Boolean),
          user_id: user?.id || "",
          mode: newProject.mode,
        }),
      })
      const data = await res.json()
      if (data.project) {
        if (newProject.folder) {
          await fetch(`http://127.0.0.1:8001/api/projects/${data.project.id}/set-folder`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder: newProject.folder }),
          })
        }
        if (newProject.mode) {
          await fetch(`http://127.0.0.1:8001/api/projects/${data.project.id}/set-mode`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: newProject.mode }),
          })
        }
        setNewProject({ name: "", codename: "", description: "", tech_stack: "", folder: "", mode: "scratch" })
        setShowCreateProject(false)
        fetchData()
      }
    } catch (e: any) {
      setError(e.message)
    }
    setCreating(false)
  }

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
          task_mode: newTask.task_mode,
        }),
      })
      if (res.ok) {
        setNewTask({ title: "", description: "", priority: "medium", project_id: "", task_mode: "developer" })
        setShowCreateTask(false)
        fetchData()
      }
    } catch (e: any) {
      setError(e.message)
    }
    setCreating(false)
  }

  const startPipeline = async (taskId: string) => {
    setError("")
    try {
      const res = await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      })
      const data = await res.json()
      if (data.error) {
        setError(data.error)
        return
      }
      fetchData()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const startTesting = async (taskId: string) => {
    setError("")
    try {
      const res = await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/start-testing`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      })
      let data: any = null
      try { data = await res.json() } catch { /* ignore */ }
      if (!res.ok) {
        setError(data?.detail || data?.error || `Request failed (HTTP ${res.status})`)
        return
      }
      if (data.error) {
        setError(data.error)
        return
      }
      fetchData()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const approvePlan = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/approve-plan`, { method: "POST" })
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
  }

  const approveDeploy = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/approve-deploy`, { method: "POST" })
  }

  const prebuiltAction = async (taskId: string, action: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/prebuilt-action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, description: prebuiltDesc }),
    })
    setPrebuiltDesc("")
    fetchData()
  }

  const solveIssues = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/solve-issues`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: prebuiltDesc }),
    })
    setPrebuiltDesc("")
    fetchData()
  }

  const stopPipeline = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/stop`, { method: "POST" })
    fetchData()
  }

  const [issueDesc, setIssueDesc] = useState("")

  const submitIssue = async (taskId: string) => {
    if (!issueDesc.trim()) return
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/submit-issue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: issueDesc }),
    })
    setIssueDesc("")
    fetchData()
  }

  const [showReplanModalTask, setShowReplanModalTask] = useState<Task | null>(null)

  useEffect(() => {
    formOpenRef.current = !!(showCreateProject || showCreateTask || editProject || editTask || showRejectModal || showReplanModalTask)
  }, [showCreateProject, showCreateTask, editProject, editTask, showRejectModal, showReplanModalTask])
  const [replanTitle, setReplanTitle] = useState("")
  const [replanDescription, setReplanDescription] = useState("")

  const startReplanModal = (task: Task) => {
    setShowReplanModalTask(task)
    setReplanTitle(task.title)
    setReplanDescription(task.description)
  }

  const submitReplanRestart = async () => {
    if (!showReplanModalTask) return
    await fetch(`http://127.0.0.1:8001/api/pipeline/${showReplanModalTask.id}/restart`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: replanTitle, description: replanDescription }),
    })
    setShowReplanModalTask(null)
    setReplanTitle("")
    setReplanDescription("")
    fetchData()
  }

  const quickRestartLayer1 = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/restart`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
    fetchData()
  }

  const deleteProject = async (projectId: string) => {
    if (!confirm("Delete this project and all its tasks?")) return
    await fetch(`http://127.0.0.1:8001/api/projects/${projectId}`, { method: "DELETE" })
    fetchData()
  }

  const deleteTask = async (taskId: string) => {
    if (!confirm("Delete this task?")) return
    await fetch(`http://127.0.0.1:8001/api/tasks/${taskId}`, { method: "DELETE" })
    fetchData()
  }

  const startEditProject = (p: Project) => {
    setEditProject(p)
    setEditName(p.name)
    setEditCodename(p.codename)
    setEditDesc(p.description)
  }

  const saveEditProject = async () => {
    if (!editProject) return
    await fetch(`http://127.0.0.1:8001/api/projects/${editProject.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: editName, codename: editCodename, description: editDesc }),
    })
    setEditProject(null)
    fetchData()
  }

  const startEditTask = (t: Task) => {
    setEditTask(t)
    setEditName(t.title)
    setEditDesc(t.description)
    setEditPriority(t.priority)
  }

  const saveEditTask = async () => {
    if (!editTask) return
    await fetch(`http://127.0.0.1:8001/api/tasks/${editTask.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: editName, description: editDesc, priority: editPriority }),
    })
    setEditTask(null)
    fetchData()
  }

  const filteredTasks = filterProject
    ? tasks.filter((t) => t.project_id === filterProject)
    : tasks

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
            <p className="text-muted-foreground">{projects.length} projects</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => { setShowCreateProject(!showCreateProject); setShowCreateTask(false); setError("") }}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
              + New Project
            </button>
            <button onClick={() => { setShowCreateTask(!showCreateTask); setShowCreateProject(false); setError("") }}
              className="rounded-lg bg-secondary px-4 py-2 text-sm font-medium">
              + New Task
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400">{error}</div>
        )}

        {showCreateProject && (
          <div className="rounded-lg border border-border bg-card p-6 space-y-4">
            <h3 className="font-semibold">New Project</h3>
            <div className="grid grid-cols-2 gap-4">
              <input placeholder="Project name" value={newProject.name} onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm" />
              <input placeholder="Codename" value={newProject.codename} onChange={(e) => setNewProject({ ...newProject, codename: e.target.value })}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm" />
            </div>
            <textarea placeholder="Description -- what this project does, what you want built..." value={newProject.description}
              onChange={(e) => setNewProject({ ...newProject, description: e.target.value })}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-24 resize-none" />

            <div>
              <label className="text-sm font-medium mb-2 block">Project Mode</label>
              <div className="grid grid-cols-2 gap-3">
                <button onClick={() => setNewProject({ ...newProject, mode: "scratch" })}
                  className={`rounded-lg border-2 p-4 text-left transition-all ${newProject.mode === "scratch"
                    ? "border-primary bg-primary/10"
                    : "border-border bg-background hover:border-border/80"}`}>
                  <div className="font-semibold text-sm mb-1">Build from Scratch</div>
                  <div className="text-xs text-muted-foreground">Agent creates a brand new project from your description</div>
                </button>
                <button onClick={() => setNewProject({ ...newProject, mode: "prebuilt" })}
                  className={`rounded-lg border-2 p-4 text-left transition-all ${newProject.mode === "prebuilt"
                    ? "border-primary bg-primary/10"
                    : "border-border bg-background hover:border-border/80"}`}>
                  <div className="font-semibold text-sm mb-1">Prebuilt</div>
                  <div className="text-xs text-muted-foreground">Agent analyzes your existing codebase and makes changes</div>
                </button>
              </div>
            </div>

            <input placeholder="Tech stack (comma separated): react, nextjs, tailwind" value={newProject.tech_stack}
              onChange={(e) => setNewProject({ ...newProject, tech_stack: e.target.value })}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />

            <div>
              <label className="text-sm font-medium mb-1 block">
                Project Folder {newProject.mode === "prebuilt" ? <span className="text-red-400">*</span> : <span className="text-muted-foreground">(optional)</span>}
              </label>
              {newProject.mode === "prebuilt" && agentConnected && agentFolder && (
                <div className="mb-2 flex items-center gap-1.5 rounded-md bg-green-500/10 border border-green-500/20 px-2.5 py-1.5 text-xs text-green-400">
                  <Monitor className="h-3.5 w-3.5" />
                  Local Agent detected — your project folder is: <span className="font-mono">{agentFolder}</span>
                </div>
              )}
              <div className="flex gap-2">
                <input value={newProject.folder} readOnly placeholder="Click Browse to select a folder..." className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono" />
                <button onClick={() => pickFolder((path) => setNewProject((p) => ({ ...p, folder: path })))}
                  className="rounded-lg bg-secondary px-3 py-2 text-sm">Browse</button>
              </div>
            </div>

            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCreateProject(false)} className="rounded-lg bg-secondary px-4 py-2 text-sm">Cancel</button>
              <button onClick={createProject} disabled={creating || !newProject.name}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                {creating ? "Creating..." : newProject.mode === "prebuilt" ? "Create & Analyze Project" : "Create Project"}
              </button>
            </div>
          </div>
        )}

        {showCreateTask && (
          <div className="rounded-lg border border-border bg-card p-6 space-y-4">
            <h3 className="font-semibold">New Task</h3>
            <input placeholder="Task title (e.g., Fix Navbar & Auth logic)" value={newTask.title} onChange={(e) => setNewTask({ ...newTask, title: e.target.value })}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
            
            {/* Quick Task Template Chips */}
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground font-medium">Quick Task Templates:</label>
              <div className="flex flex-wrap gap-1.5">
                {[
                  { title: "Fix Build & TypeScript Errors", desc: "Scan project for TypeScript and build errors, fix all broken imports, and verify clean compilation." },
                  { title: "Refactor Frontend UI & Layout", desc: "Improve responsiveness, clean up CSS/Tailwind classes, and fix broken React component states." },
                  { title: "Fix Backend API & Endpoints", desc: "Check server routes, database queries, and async error handling across all backend controllers." },
                ].map((template, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setNewTask({ ...newTask, title: template.title, description: template.desc })}
                    className="text-xs bg-secondary hover:bg-secondary/80 border border-border px-2.5 py-1 rounded-md text-foreground transition-colors"
                  >
                    + {template.title}
                  </button>
                ))}
              </div>
            </div>

            <textarea placeholder="Task details -- what needs to be done..." value={newTask.description}
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

            <div>
              <label className="text-xs text-muted-foreground font-medium">Task Team:</label>
              <div className="flex gap-3 mt-1.5">
                <label className={`flex-1 rounded-lg border p-3 cursor-pointer ${newTask.task_mode === "developer" ? "border-blue-500 bg-blue-500/10" : "border-border"}`}>
                  <input type="radio" name="task_mode" value="developer" checked={newTask.task_mode === "developer"}
                    onChange={() => setNewTask({ ...newTask, task_mode: "developer" })} className="hidden" />
                  <div className="font-semibold text-sm">Development Team</div>
                  <p className="text-xs text-muted-foreground mt-1">Agent plans, builds and fixes the project (normal flow)</p>
                </label>
                <label className={`flex-1 rounded-lg border p-3 cursor-pointer ${newTask.task_mode === "tester" ? "border-emerald-500 bg-emerald-500/10" : "border-border"}`}>
                  <input type="radio" name="task_mode" value="tester" checked={newTask.task_mode === "tester"}
                    onChange={() => setNewTask({ ...newTask, task_mode: "tester" })} className="hidden" />
                  <div className="font-semibold text-sm">Tester Team</div>
                  <p className="text-xs text-muted-foreground mt-1">Agent only tests & checks the project (browser included) and reports issues</p>
                </label>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCreateTask(false)} className="rounded-lg bg-secondary px-4 py-2 text-sm">Cancel</button>
              <button onClick={createTask} disabled={creating || !newTask.title}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                Create Task
              </button>
            </div>
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <div key={project.id} className="rounded-lg border border-border bg-card p-4 space-y-2">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold">{project.name}</h3>
                  <p className="text-xs text-muted-foreground">{project.codename}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  project.mode === "prebuilt" ? "bg-cyan-500/10 text-cyan-400" : "bg-blue-500/10 text-blue-400"
                }`}>{project.mode === "prebuilt" ? "Pre-built" : "Scratch"}</span>
              </div>
              {project.description && <p className="text-xs text-muted-foreground">{project.description}</p>}
              {project.folder && <p className="text-xs text-green-400 font-mono truncate">{project.folder}</p>}
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span>{project.tasks_count} tasks</span>
                <span>{project.status}</span>
              </div>
              <div className="flex gap-1">
                <button onClick={() => pickFolder(async (path) => {
                    await fetch(`http://127.0.0.1:8001/api/projects/${project.id}/set-folder`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ folder: path }),
                    })
                    fetchData()
                  })}
                  className="text-xs bg-secondary px-2 py-1 rounded hover:bg-secondary/80">{project.folder ? "Change Folder" : "Set Folder"}</button>
                <button onClick={() => startEditProject(project)}
                  className="text-xs bg-secondary px-2 py-1 rounded hover:bg-secondary/80">Edit</button>
                <button onClick={() => deleteProject(project.id)}
                  className="text-xs bg-red-600/20 text-red-400 px-2 py-1 rounded hover:bg-red-600/30">Delete</button>
              </div>
            </div>
          ))}
        </div>

        {projects.length > 0 && (
          <select value={filterProject} onChange={(e) => setFilterProject(e.target.value)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm">
            <option value="">All Projects</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        )}

        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Tasks</h2>
          {filteredTasks.length === 0 && <p className="text-sm text-muted-foreground">No tasks yet. Create one above.</p>}
          {filteredTasks.map((task) => {
            const pipeline = pipelineTasks[task.id]
            const stage = pipeline?.stage || "idle"
            const isExpanded = expandedTask === task.id
            return (
              <div key={task.id} className="rounded-lg border border-border bg-card overflow-hidden">
                <button onClick={() => setExpandedTask(isExpanded ? null : task.id)}
                  className="w-full text-left p-4 flex items-start justify-between hover:bg-secondary/30 transition-colors">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <svg className={`h-4 w-4 text-muted-foreground shrink-0 transition-transform ${isExpanded ? "rotate-90" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                      <h4 className="font-semibold text-sm">
                        {task.title}{" "}
                        {task.task_mode === "tester" && (
                          <span className="ml-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 align-middle">
                            Tester
                          </span>
                        )}
                      </h4>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 ml-6 line-clamp-1">{task.description}</p>
                    {task.project_id && (
                      <p className="text-xs text-muted-foreground mt-1 ml-6">
                        Project: {projects.find((p) => p.id === task.project_id)?.name || task.project_id}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-2">
                    {pipeline && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${stageColors[stage]}`}>
                        {stageLabels[stage] || stage}
                      </span>
                    )}
                  </div>
                </button>

                {isExpanded && (<div className="px-4 pb-4 space-y-3 border-t border-border pt-3 ml-6">
                  {!pipeline && (
                    <div className="flex items-center gap-2 flex-wrap">
                      {task.task_mode === "tester" ? (
                        <>
                          <button onClick={() => startTesting(task.id)}
                            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 shadow-sm">
                            🧪 Start Testing
                          </button>
                          <button onClick={() => router.push("/tester")}
                            className="text-xs bg-secondary px-2 py-1 rounded hover:bg-secondary/80">
                            Open Tester Page
                          </button>
                        </>
                      ) : (
                        <>
                          <button onClick={() => startPipeline(task.id)}
                            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 shadow-sm">
                            🚀 Start Building
                          </button>
                          <button onClick={() => startReplanModal(task)}
                            className="rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/30 px-3 py-2 text-sm font-medium hover:bg-amber-500/30 transition-colors">
                            🔄 Edit & Start (Layer 1)
                          </button>
                        </>
                      )}
                    </div>
                  )}

                  {pipeline && (
                  <div className="space-y-3 border-t border-border pt-3">
                    {pipeline.current_agent && (
                      <div className="flex items-center gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2">
                        <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
                        <span className="text-xs font-bold text-blue-300 uppercase">{pipeline.current_agent}</span>
                        <span className="text-xs text-blue-200">{pipeline.current_action}</span>
                      </div>
                    )}
                    <div className="flex items-center gap-2 flex-wrap">
                      <button onClick={() => router.push(`/monitor?task=${task.id}`)}
                        className="text-xs text-primary hover:underline font-medium">
                        Open in Monitor
                      </button>
                      <button onClick={() => startReplanModal(task)}
                        className="text-xs bg-amber-500/20 text-amber-300 border border-amber-500/30 font-medium px-2 py-0.5 rounded hover:bg-amber-500/30 transition-colors">
                        🔄 Try Again / Edit (Layer 1)
                      </button>
                      <button onClick={() => quickRestartLayer1(task.id)}
                        className="text-xs bg-secondary border border-border font-medium px-2 py-0.5 rounded hover:bg-secondary/80 transition-colors">
                        ⚡ Quick Restart
                      </button>
                      {["building", "planning", "checking", "deploying", "awaiting_plan_approval"].includes(stage) && (
                        <button onClick={() => stopPipeline(task.id)}
                          className="text-xs bg-red-600/20 text-red-400 px-2 py-0.5 rounded hover:bg-red-600/30">
                          Stop Build
                        </button>
                      )}
                      <button onClick={() => startEditTask(task)}
                        className="text-xs bg-secondary px-2 py-0.5 rounded hover:bg-secondary/80">
                        Edit
                      </button>
                      <button onClick={() => deleteTask(task.id)}
                        className="text-xs bg-red-600/20 text-red-400 px-2 py-0.5 rounded hover:bg-red-600/30">
                        Delete
                      </button>
                    </div>
                    <div className="space-y-2 rounded-lg border border-border bg-secondary/30 p-3">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Ask the Agent (Add / Remove / Change)</label>
                        <span className="text-[10px] text-muted-foreground">Click a quick template or type below</span>
                      </div>

                      {/* Quick Prompt Preset Chips */}
                      <div className="flex flex-wrap gap-1.5 py-1">
                        {[
                          "➕ Add a new page / feature",
                          "➖ Remove a page / feature",
                          "✏️ Change / update existing code",
                          "🛠️ Fix build and runtime errors",
                          "🎨 Fix responsive UI styling & components",
                          "⚡ Fix API routes and data fetching",
                          "🔒 Add error handling and input validation",
                          "🧪 Check code quality & fix bugs",
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
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-16 resize-none"
                      />
                      <div className="flex items-center gap-2">
                        <button onClick={() => submitIssue(task.id)}
                          disabled={!issueDesc.trim()}
                          className="rounded-lg bg-amber-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-40 disabled:cursor-not-allowed">
                          Ask Agent
                        </button>
                        <span className="text-[10px] text-muted-foreground">Works anytime — even after the build is complete or failed.</span>
                      </div>
                    </div>

                    {stage === "awaiting_plan_approval" && (
                      <div className="space-y-2">
                        <div className="rounded-lg bg-secondary p-3 text-xs" dangerouslySetInnerHTML={{ __html: formatMd(pipeline.plan_content) }} />
                        <div className="flex gap-2 flex-wrap">
                          <button onClick={() => approvePlan(task.id)}
                            className="rounded-lg bg-green-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-green-700">
                            Approve Plan
                          </button>
                          <button onClick={() => rejectPlan(task.id)}
                            className="rounded-lg bg-red-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-red-700">
                            Reject & Redo
                          </button>
                          <button onClick={() => startReplanModal(task)}
                            className="rounded-lg bg-amber-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 shadow-sm">
                            🔄 Edit & Re-Plan (Layer 1)
                          </button>
                        </div>
                      </div>
                    )}

                    {stage === "awaiting_check_approval" && (
                      <div className="space-y-2">
                        <div className="rounded-lg bg-secondary p-3 text-xs" dangerouslySetInnerHTML={{ __html: formatMd(pipeline.check_output) }} />
                        <div className="flex gap-2">
                          <button onClick={() => approveDeploy(task.id)}
                            className="rounded-lg bg-cyan-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-cyan-700">
                            Deploy
                          </button>
                          <button onClick={() => startReplanModal(task)}
                            className="rounded-lg bg-amber-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-amber-700">
                            🔄 Try Again / Edit
                          </button>
                        </div>
                      </div>
                    )}

                    {stage === "awaiting_prebuilt_action" && (
                      <div className="space-y-2">
                        {pipeline.check_output && (
                          <div className="rounded-lg bg-secondary p-3 text-xs" dangerouslySetInnerHTML={{ __html: formatMd(pipeline.check_output) }} />
                        )}
                        <textarea
                          value={prebuiltDesc}
                          onChange={(e) => setPrebuiltDesc(e.target.value)}
                          placeholder="Optional: Describe specific issues, changes, or what you want the agent to focus on..."
                          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-16 resize-none"
                        />
                        <div className="flex flex-wrap gap-2">
                          <button onClick={() => prebuiltAction(task.id, "analyze")}
                            className="rounded-lg bg-orange-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-orange-700">
                            Analyze Issues
                          </button>
                          <button onClick={() => prebuiltAction(task.id, "complete")}
                            className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700">
                            Complete Project
                          </button>
                          <button onClick={() => prebuiltAction(task.id, "deploy")}
                            className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-700">
                            Deploy
                          </button>
                          <button onClick={() => prebuiltAction(task.id, "run")}
                            className="rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700">
                            How to Run
                          </button>
                          <button onClick={() => startReplanModal(task)}
                            className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700">
                            🔄 Try Again & Edit
                          </button>
                          {pipeline.check_output && pipeline.check_output.includes("issue") && (
                            <button onClick={() => solveIssues(task.id)}
                              className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700">
                              Solve Issues
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {stage === "completed" && (
                      <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-3 flex items-center justify-between">
                        <p className="text-xs text-green-400 font-semibold">Project Complete!</p>
                        <button onClick={() => startReplanModal(task)}
                          className="rounded-lg bg-amber-600/20 text-amber-300 border border-amber-500/30 px-3 py-1 text-xs font-medium hover:bg-amber-600/30">
                          🔄 Re-run / Add Features
                        </button>
                      </div>
                    )}

                    {stage === "failed" && (
                      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-xs text-red-400 font-bold uppercase">❌ Pipeline Stopped / Failed</p>
                          <span className="text-[10px] text-red-300 bg-red-500/20 px-2 py-0.5 rounded">Attempt #{pipeline.rejection_count || 1}</span>
                        </div>
                        <p className="text-xs text-red-300 bg-background/50 p-2 rounded border border-red-500/20 font-mono">{pipeline.error}</p>
                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          <button onClick={() => startReplanModal(task)}
                            className="rounded-lg bg-amber-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 shadow-sm transition-colors">
                            🔄 Try Again & Edit (Restart from Layer 1)
                          </button>
                          <button onClick={() => quickRestartLayer1(task.id)}
                            className="rounded-lg bg-secondary border border-border px-3.5 py-1.5 text-xs font-medium text-foreground hover:bg-secondary/80 transition-colors">
                            ⚡ Quick Restart from Layer 1
                          </button>
                        </div>
                      </div>
                    )}

                    {pipeline.files_written && pipeline.files_written.length > 0 && (
                      <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-2">
                        <p className="text-xs font-semibold text-green-400">Files Written: {pipeline.files_written.length}</p>
                        {pipeline.files_written.map((f, i) => (
                          <p key={i} className="text-xs text-green-300 font-mono">{f.path}</p>
                        ))}
                      </div>
                    )}

                    {pipeline.build_output && (
                      <details className="text-xs">
                        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">View Build Output</summary>
                        <div className="mt-2 rounded-lg bg-secondary p-3" dangerouslySetInnerHTML={{ __html: formatMd(pipeline.build_output.slice(0, 3000)) }} />
                      </details>
                    )}

                    {pipeline.history && pipeline.history.length > 0 && (
                      <details className="text-xs">
                        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">View History</summary>
                        <div className="mt-2 space-y-1">
                          {pipeline.history.map((h, i) => (
                            <div key={i} className="flex gap-2 text-xs">
                              <span className="text-muted-foreground">{new Date(h.timestamp).toLocaleTimeString()}</span>
                              <span className="text-foreground">{h.message}</span>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                )}
                </div>)}
              </div>
            )
          })}
        </div>

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

        {editProject && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="rounded-xl border border-border bg-card p-6 w-full max-w-md space-y-4">
              <h3 className="font-semibold">Edit Project</h3>
              <input value={editName} onChange={(e) => setEditName(e.target.value)} placeholder="Project name"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
              <input value={editCodename} onChange={(e) => setEditCodename(e.target.value)} placeholder="Codename"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
              <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)} placeholder="Description"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-20 resize-none" />
              <div className="flex gap-2 justify-end">
                <button onClick={() => setEditProject(null)} className="rounded-lg bg-secondary px-4 py-2 text-sm">Cancel</button>
                <button onClick={saveEditProject} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">Save</button>
              </div>
            </div>
          </div>
        )}

        {editTask && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="rounded-xl border border-border bg-card p-6 w-full max-w-md space-y-4">
              <h3 className="font-semibold">Edit Task</h3>
              <input value={editName} onChange={(e) => setEditName(e.target.value)} placeholder="Task title"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
              <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)} placeholder="Description"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-20 resize-none" />
              <select value={editPriority} onChange={(e) => setEditPriority(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm w-full">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
              <div className="flex gap-2 justify-end">
                <button onClick={() => setEditTask(null)} className="rounded-lg bg-secondary px-4 py-2 text-sm">Cancel</button>
                <button onClick={saveEditTask} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">Save</button>
              </div>
            </div>
          </div>
        )}

        {/* Re-plan & Restart from Layer 1 Modal */}
        {showReplanModalTask && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
            <div className="w-full max-w-lg rounded-xl border border-amber-500/30 bg-card p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div>
                  <h3 className="text-lg font-bold text-amber-400">🔄 Try Again & Edit (Restart from Layer 1)</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">Modify your prompt or instructions and restart from Layer 1 (Planning).</p>
                </div>
                <button onClick={() => setShowReplanModalTask(null)} className="text-muted-foreground hover:text-foreground text-sm font-bold">✕</button>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="text-xs font-semibold text-muted-foreground uppercase">Task Title</label>
                  <input
                    type="text"
                    value={replanTitle}
                    onChange={(e) => setReplanTitle(e.target.value)}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm mt-1 font-medium"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-muted-foreground uppercase">Project Instructions / Requirements (Layer 1 Prompt)</label>
                  <textarea
                    value={replanDescription}
                    onChange={(e) => setReplanDescription(e.target.value)}
                    placeholder="Update what needs to be built..."
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-32 resize-y mt-1"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 border-t border-border pt-4">
                <button
                  onClick={() => setShowReplanModalTask(null)}
                  className="rounded-lg bg-secondary px-4 py-2 text-sm font-medium hover:bg-secondary/80"
                >
                  Cancel
                </button>
                <button
                  onClick={submitReplanRestart}
                  className="rounded-lg bg-amber-600 px-5 py-2 text-sm font-semibold text-white hover:bg-amber-700 shadow-md transition-colors"
                >
                  🚀 Save & Restart from Layer 1 (Planning)
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
