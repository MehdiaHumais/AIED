"use client"

import { useEffect, useState, useRef } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"

interface PipelineTask {
  task_id: string
  project_id: string
  title: string
  description: string
  stage: string
  build_output: string
  check_output: string
  deploy_output: string
  error: string
  files_written: { path: string; size: number }[]
  history: { stage: string; message: string; timestamp: string }[]
  current_agent: string
  current_action: string
  todo_list: { id: number; description: string; status: string }[]
}

interface Project {
  id: string
  name: string
  codename: string
  description: string
  status: string
  tech_stack: string[]
  tasks_count: number
  created_at: string
  mode: string
  folder: string
}

const stageColors: Record<string, string> = {
  idle: "bg-gray-500/10 text-gray-400 border-gray-500/30",
  planning: "bg-purple-500/10 text-purple-400 border-purple-500/30",
  awaiting_plan_approval: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  building: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  checking: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  awaiting_check_approval: "bg-green-500/10 text-green-400 border-green-500/30",
  deploying: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
  completed: "bg-green-500/10 text-green-400 border-green-500/30",
  failed: "bg-red-500/10 text-red-400 border-red-500/30",
  awaiting_prebuilt_action: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  analyzing: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  fixing: "bg-blue-500/10 text-blue-400 border-blue-500/30",
}

const stageLabels: Record<string, string> = {
  idle: "Ready",
  planning: "Planning",
  awaiting_plan_approval: "Awaiting Approval",
  building: "Building",
  checking: "Validating",
  awaiting_check_approval: "Ready to Deploy",
  deploying: "Deploying",
  completed: "Completed",
  failed: "Failed",
  awaiting_prebuilt_action: "Choose Action",
  analyzing: "Analyzing",
  fixing: "Fixing Issues",
}

export default function DeploymentsPage() {
  const [pipelines, setPipelines] = useState<Record<string, PipelineTask>>({})
  const [projects, setProjects] = useState<Project[]>([])
  const [showDeployModal, setShowDeployModal] = useState<string | null>(null)
  const [selectedTask, setSelectedTask] = useState<string>("")
  const [deployForm, setDeployForm] = useState({
    apk_path: "",
    package_name: "",
    version: "",
    version_code: "1",
    release_notes: "",
    app_name: "",
    mode: "auto",
    featured: false,
    published: false,
  })
  const [deploying, setDeploying] = useState(false)
  const [deployResult, setDeployResult] = useState<string>("")
  const [checkingPkg, setCheckingPkg] = useState(false)
  const [showBrowser, setShowBrowser] = useState(false)
  const [browserDir, setBrowserDir] = useState("")
  const [browserFiles, setBrowserFiles] = useState<{name: string; path: string; size?: number; is_dir?: boolean}[]>([])
  const [browserLoading, setBrowserLoading] = useState(false)
  const [mediaPkg, setMediaPkg] = useState("")
  const [mediaIcon, setMediaIcon] = useState<File | null>(null)
  const [mediaMobile, setMediaMobile] = useState<File[]>([])
  const [mediaTablet, setMediaTablet] = useState<File[]>([])
  const [mediaUploading, setMediaUploading] = useState(false)
  const [mediaResult, setMediaResult] = useState("")
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  const fetchData = () => {
    fetch("http://127.0.0.1:8001/api/pipelines")
      .then((r) => r.json())
      .then((data) => setPipelines(data.pipelines || {}))
      .catch(() => {})

    fetch("http://127.0.0.1:8001/api/projects")
      .then((r) => r.json())
      .then((data) => setProjects(data.projects || []))
      .catch(() => {})
  }

  useEffect(() => {
    fetchData()
    pollRef.current = setInterval(fetchData, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const taskList = Object.values(pipelines)
  const completedTasks = taskList.filter((t) => t.stage === "completed")
  const activeTasks = taskList.filter((t) => !["idle", "completed", "failed"].includes(t.stage))
  const failedTasks = taskList.filter((t) => t.stage === "failed")

  const browseApk = async (dir?: string) => {
    setBrowserLoading(true)
    setShowBrowser(true)
    try {
      const url = dir ? `http://127.0.0.1:8001/api/browse-apk?directory=${encodeURIComponent(dir)}` : "http://127.0.0.1:8001/api/browse-apk"
      const res = await fetch(url)
      const data = await res.json()
      if (data.error) {
        setDeployResult(`Browse error: ${data.error}`)
        setShowBrowser(false)
      } else {
        setBrowserDir(data.directory)
        setBrowserFiles(data.files || [])
      }
    } catch (err) {
      setDeployResult(`Could not connect to backend: ${err}`)
      setShowBrowser(false)
    }
    setBrowserLoading(false)
  }

  const openDeployModal = (taskId: string, task: PipelineTask) => {
    setSelectedTask(taskId)
    setDeployForm({
      apk_path: "",
      package_name: task.title ? task.title.toLowerCase().replace(/[^a-z0-9]/g, ".") : "",
      version: "1.0.0",
      version_code: "1",
      release_notes: "",
      app_name: task.title || "",
      mode: "auto",
      featured: false,
      published: false,
    })
    setDeployResult("")
    setShowDeployModal(taskId)
  }

  const checkPackage = async () => {
    if (!deployForm.package_name) {
      setDeployResult("Enter a package name first.")
      return
    }
    setCheckingPkg(true)
    setDeployResult("Checking store...")
    try {
      const res = await fetch(`http://127.0.0.1:8001/api/store/check-package/${encodeURIComponent(deployForm.package_name)}`)
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: "Request failed" }))
        setDeployResult(`Check failed: ${err.error || res.statusText}`)
        setCheckingPkg(false)
        return
      }
      const data = await res.json()
      if (data.exists) {
        setDeployResult(`Package "${deployForm.package_name}" EXISTS in store. Will upload new version.`)
        setDeployForm({ ...deployForm, mode: "update" })
      } else {
        setDeployResult(`Package "${deployForm.package_name}" NOT found. Will create new app listing.`)
        setDeployForm({ ...deployForm, mode: "new" })
      }
    } catch (err) {
      setDeployResult(`Could not reach store: ${err}`)
    }
    setCheckingPkg(false)
  }

  const uploadMedia = async () => {
    if (!mediaPkg) {
      setMediaResult("Enter package name.")
      return
    }
    setMediaUploading(true)
    setMediaResult("Uploading...")
    try {
      const fd = new FormData()
      fd.append("package_name", mediaPkg)
      if (mediaIcon) fd.append("icon", mediaIcon)
      for (const f of mediaMobile) fd.append("mobile_screenshots", f)
      for (const f of mediaTablet) fd.append("tablet_screenshots", f)
      const res = await fetch("http://127.0.0.1:8001/api/store/upload-media", { method: "POST", body: fd })
      const data = await res.json()
      if (data.error) {
        setMediaResult(`Error: ${data.error}`)
      } else {
        setMediaResult(`Done! Icon: ${data.icon_updated ? "uploaded" : "unchanged"}, Screenshots: ${data.screenshots_added} added`)
        setMediaIcon(null)
        setMediaMobile([])
        setMediaTablet([])
      }
    } catch (err) {
      setMediaResult(`Failed: ${err}`)
    }
    setMediaUploading(false)
  }

  const deployToStore = async () => {
    if (!deployForm.apk_path) {
      setDeployResult("APK file path is required.")
      return
    }
    setDeploying(true)
    setDeployResult("Deploying...")
    try {
      let url: string
      let body: Record<string, unknown>
      if (selectedTask && selectedTask !== "new") {
        url = `http://127.0.0.1:8001/api/pipeline/${selectedTask}/deploy-to-store`
        body = deployForm
      } else {
        url = `http://127.0.0.1:8001/api/deploy-apk`
        body = deployForm
      }
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (data.error) {
        setDeployResult(`Error: ${data.error}`)
      } else {
        const msg = data.message || "Deployed successfully!"
        setDeployResult(msg)
        if (data.success) {
          setTimeout(() => {
            setShowDeployModal(null)
            fetchData()
          }, 3000)
        }
      }
    } catch (err) {
      setDeployResult(`Failed: ${err}`)
    }
    setDeploying(false)
  }

  const approveDeploy = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/approve-deploy`, { method: "POST" })
    fetchData()
  }

  const startPipeline = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/start`, { method: "POST" })
    fetchData()
  }

  const stopPipeline = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}/stop`, { method: "POST" })
    fetchData()
  }

  const deletePipeline = async (taskId: string) => {
    await fetch(`http://127.0.0.1:8001/api/pipeline/${taskId}`, { method: "DELETE" })
    fetchData()
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Store Deployments</h1>
            <p className="text-muted-foreground">Deploy apps to BritStore and manage releases</p>
          </div>
          <button
            onClick={() => { setShowDeployModal("new"); setSelectedTask(""); setDeployForm({ apk_path: "", package_name: "", version: "1.0.0", version_code: "1", release_notes: "", app_name: "", mode: "auto", featured: false, published: false }); setDeployResult(""); setShowBrowser(false) }}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            + Deploy APK
          </button>
        </div>

        {/* Stats */}
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Total Deployments</p>
            <p className="text-2xl font-bold">{taskList.length}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Completed</p>
            <p className="text-2xl font-bold text-green-400">{completedTasks.length}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">In Progress</p>
            <p className="text-2xl font-bold text-blue-400">{activeTasks.length}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Failed</p>
            <p className="text-2xl font-bold text-red-400">{failedTasks.length}</p>
          </div>
        </div>

        {/* Active Deployments */}
        {activeTasks.length > 0 && (
          <div className="rounded-lg border border-border bg-card p-6">
            <h2 className="text-lg font-semibold mb-4 text-blue-400">Active Deployments</h2>
            <div className="space-y-3">
              {activeTasks.map((task) => (
                <div key={task.task_id} className="rounded border border-border p-4 bg-blue-500/5">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h4 className="font-medium">{task.title}</h4>
                      <p className="text-xs text-muted-foreground">{task.description}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`text-xs px-3 py-1 rounded-full border ${stageColors[task.stage] || stageColors.idle}`}>
                        {stageLabels[task.stage] || task.stage}
                      </span>
                      {task.current_agent && (
                        <span className="text-xs text-muted-foreground">{task.current_agent}</span>
                      )}
                      <button onClick={() => stopPipeline(task.task_id)}
                        className="text-xs bg-red-500/10 text-red-400 px-3 py-1.5 rounded hover:bg-red-500/20">
                        Stop
                      </button>
                      <button onClick={() => deletePipeline(task.task_id)}
                        className="text-xs bg-red-500/10 text-red-400 px-3 py-1.5 rounded hover:bg-red-500/20">
                        Delete
                      </button>
                    </div>
                  </div>
                  {task.todo_list && task.todo_list.length > 0 && (
                    <div className="mt-2 text-xs text-muted-foreground">
                      {task.todo_list.filter((t) => t.status === "completed").length}/{task.todo_list.length} tasks completed
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Completed Deployments */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">Project Deployments</h2>
          {taskList.length === 0 && projects.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground mb-2">No deployments yet</p>
              <p className="text-xs text-muted-foreground">Create a project and run the pipeline, or deploy an APK directly.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {completedTasks.map((task) => (
                <div key={task.task_id} className="flex items-center justify-between rounded border border-border p-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <h4 className="font-medium">{task.title}</h4>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 border border-green-500/30">
                        Completed
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{task.description}</p>
                    {task.deploy_output && (
                      <p className="text-xs text-emerald-400 mt-1 font-mono truncate max-w-lg">{task.deploy_output}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <button onClick={() => openDeployModal(task.task_id, task)}
                      className="text-xs bg-emerald-500/10 text-emerald-400 px-3 py-1.5 rounded hover:bg-emerald-500/20 border border-emerald-500/30">
                      Deploy to Store
                    </button>
                    <button onClick={() => deletePipeline(task.task_id)}
                      className="text-xs bg-red-500/10 text-red-400 px-3 py-1.5 rounded hover:bg-red-500/20">
                      Delete
                    </button>
                  </div>
                </div>
              ))}

              {failedTasks.map((task) => (
                <div key={task.task_id} className="flex items-center justify-between rounded border border-border p-4 bg-red-500/5">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <h4 className="font-medium">{task.title}</h4>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/30">
                        Failed
                      </span>
                    </div>
                    <p className="text-xs text-red-400 mt-1">{task.error}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <button onClick={() => startPipeline(task.task_id)}
                      className="text-xs bg-secondary px-3 py-1.5 rounded hover:bg-secondary/80">
                      Retry
                    </button>
                    <button onClick={() => openDeployModal(task.task_id, task)}
                      className="text-xs bg-emerald-500/10 text-emerald-400 px-3 py-1.5 rounded hover:bg-emerald-500/20 border border-emerald-500/30">
                      Deploy to Store
                    </button>
                    <button onClick={() => deletePipeline(task.task_id)}
                      className="text-xs bg-red-500/10 text-red-400 px-3 py-1.5 rounded hover:bg-red-500/20">
                      Delete
                    </button>
                  </div>
                </div>
              ))}

              {taskList.length === 0 && projects.map((project) => (
                <div key={project.id} className="flex items-center justify-between rounded border border-border p-4">
                  <div>
                    <h4 className="font-medium">{project.name}</h4>
                    <p className="text-xs text-muted-foreground">{project.codename}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`text-xs px-3 py-1 rounded-full ${
                      project.status === "in_progress" ? "bg-blue-500/10 text-blue-500" :
                      project.status === "completed" ? "bg-green-500/10 text-green-500" :
                      "bg-gray-500/10 text-gray-400"
                    }`}>
                      {project.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* App Media Upload - Icon & Screenshots */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-2">App Media (Icon & Screenshots)</h2>
          <p className="text-xs text-muted-foreground mb-4">Upload icon and screenshots for an app already on the store. After deploying a new APK, use this to add visuals.</p>
          <div className="space-y-3 max-w-lg">
            <div>
              <label className="text-xs text-muted-foreground">Package Name *</label>
              <input value={mediaPkg} onChange={(e) => setMediaPkg(e.target.value)}
                placeholder="com.britsync.myapp"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">App Icon (PNG, JPG)</label>
              <input type="file" accept="image/*" onChange={(e) => setMediaIcon(e.target.files?.[0] || null)}
                className="w-full text-sm text-muted-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-emerald-600 file:px-3 file:py-1 file:text-xs file:text-white file:cursor-pointer" />
              {mediaIcon && <p className="text-xs text-emerald-400 mt-1">{mediaIcon.name}</p>}
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Mobile Screenshots (at least 7 recommended)</label>
              <input type="file" accept="image/*" multiple onChange={(e) => setMediaMobile(Array.from(e.target.files || []))}
                className="w-full text-sm text-muted-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-blue-600 file:px-3 file:py-1 file:text-xs file:text-white file:cursor-pointer" />
              {mediaMobile.length > 0 && <p className="text-xs text-blue-400 mt-1">{mediaMobile.length} files selected</p>}
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Tablet Screenshots (optional)</label>
              <input type="file" accept="image/*" multiple onChange={(e) => setMediaTablet(Array.from(e.target.files || []))}
                className="w-full text-sm text-muted-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-purple-600 file:px-3 file:py-1 file:text-xs file:text-white file:cursor-pointer" />
              {mediaTablet.length > 0 && <p className="text-xs text-purple-400 mt-1">{mediaTablet.length} files selected</p>}
            </div>
            {mediaResult && (
              <div className={`text-sm p-3 rounded-lg ${
                mediaResult.startsWith("Error") || mediaResult.startsWith("Failed")
                  ? "bg-red-500/10 text-red-400 border border-red-500/30"
                  : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
              }`}>{mediaResult}</div>
            )}
            <button onClick={uploadMedia} disabled={!mediaPkg || mediaUploading}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
              {mediaUploading ? "Uploading..." : "Upload Media to Store"}
            </button>
          </div>
        </div>

        {/* Deploy Modal */}
        {showDeployModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="rounded-xl border border-border bg-card p-6 w-full max-w-lg space-y-4 max-h-[90vh] overflow-y-auto">
              <h3 className="font-semibold text-emerald-400">Deploy to BritStore</h3>

              {/* Mode selector */}
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
                {deployForm.mode === "new" && "Creates a new store listing. You MUST add icon + screenshots via store dashboard after upload."}
              </div>

              <div className="space-y-3">
                {/* APK File Picker */}
                <div>
                  <label className="text-xs text-muted-foreground">APK File *</label>
                  <div className="flex gap-2">
                    <input value={deployForm.apk_path} onChange={(e) => setDeployForm({ ...deployForm, apk_path: e.target.value })}
                      placeholder="Type path or click Browse..."
                      className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                    <button onClick={() => browseApk()}
                      className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 whitespace-nowrap">
                      Browse
                    </button>
                  </div>

                  {/* File browser panel */}
                  {showBrowser && (
                    <div className="mt-2 rounded-lg border border-border bg-background max-h-48 overflow-y-auto">
                      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-secondary/50 sticky top-0">
                        <span className="text-xs text-muted-foreground font-mono truncate">{browserDir}</span>
                        <button onClick={() => setShowBrowser(false)} className="text-xs text-muted-foreground hover:text-foreground ml-2">X</button>
                      </div>
                      {browserLoading ? (
                        <div className="p-3 text-xs text-muted-foreground">Loading...</div>
                      ) : (
                        <div className="p-1">
                          {browserFiles.map((f, i) => (
                            <button key={i} onClick={() => {
                              if (f.is_dir) {
                                browseApk(f.path)
                              } else {
                                setDeployForm({ ...deployForm, apk_path: f.path })
                                setShowBrowser(false)
                              }
                            }}
                              className={`w-full text-left px-3 py-1.5 text-sm rounded hover:bg-secondary flex items-center justify-between ${f.name.endsWith("/") ? "text-blue-400" : f.name.toLowerCase().endsWith(".apk") ? "text-emerald-400" : "text-muted-foreground"}`}>
                              <span className="truncate">{f.is_dir ? "[Dir] " : ""}{f.name}</span>
                              {f.size !== undefined && !f.is_dir && (
                                <span className="text-xs text-muted-foreground ml-2 whitespace-nowrap">
                                  {f.size > 1048576 ? (f.size / 1048576).toFixed(1) + " MB" : (f.size / 1024).toFixed(0) + " KB"}
                                </span>
                              )}
                            </button>
                          ))}
                          {browserFiles.length === 0 && (
                            <div className="p-3 text-xs text-muted-foreground">No APK files found in this directory</div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Package Name + Check Button - same row */}
                <div>
                  <label className="text-xs text-muted-foreground">Package Name</label>
                  <div className="flex gap-2">
                    <input value={deployForm.package_name} onChange={(e) => setDeployForm({ ...deployForm, package_name: e.target.value })}
                      placeholder={deployForm.mode === "new" ? "Optional (auto-detect from APK)" : "com.britsync.myapp"}
                      className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                    <button onClick={checkPackage} disabled={!deployForm.package_name || checkingPkg}
                      className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap">
                      {checkingPkg ? "Checking..." : "Check Store"}
                    </button>
                  </div>
                </div>

                {/* Version + Version Code */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-muted-foreground">Version</label>
                    <input value={deployForm.version} onChange={(e) => setDeployForm({ ...deployForm, version: e.target.value })}
                      placeholder="1.0.0"
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Version Code</label>
                    <input value={deployForm.version_code} onChange={(e) => setDeployForm({ ...deployForm, version_code: e.target.value })}
                      placeholder="1" type="number"
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                  </div>
                </div>

                {deployForm.mode !== "new" && (
                  <div>
                    <label className="text-xs text-muted-foreground">App Name</label>
                    <input value={deployForm.app_name} onChange={(e) => setDeployForm({ ...deployForm, app_name: e.target.value })}
                      placeholder="My App"
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
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

              {/* Result / Status */}
              {deployResult && (
                <div className={`text-sm p-3 rounded-lg whitespace-pre-wrap ${
                  deployResult.startsWith("Error") || deployResult.startsWith("Failed") || deployResult.startsWith("Check failed") || deployResult.startsWith("Could not") || deployResult.includes("error")
                    ? "bg-red-500/10 text-red-400 border border-red-500/30"
                    : deployResult.startsWith("Checking") || deployResult.startsWith("Deploying")
                    ? "bg-blue-500/10 text-blue-400 border border-blue-500/30"
                    : deployResult.includes("NEXT STEPS") || deployResult.includes("icon") || deployResult.includes("screenshots")
                    ? "bg-yellow-500/10 text-yellow-400 border border-yellow-500/30"
                    : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                }`}>
                  {deployResult}
                </div>
              )}

              <div className="flex gap-2 justify-end">
                <button onClick={() => setShowDeployModal(null)}
                  className="rounded-lg bg-secondary px-4 py-2 text-sm">Cancel</button>
                <button onClick={deployToStore}
                  disabled={!deployForm.apk_path || deploying}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                  {deploying ? "Deploying..." : "Deploy to Store"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
