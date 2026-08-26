"use client"

import { useEffect, useState, useRef } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"

const API = "http://127.0.0.1:8001"

interface Deployment {
  id: string
  project_name: string
  github_repo: string
  branch: string
  domain: string
  vps_host: string
  vps_username: string
  status: string
  deploy_mode: string
  deploy_strategy: string
  detected_stack: Record<string, any>
  deployment_plan: string
  commit_sha: string
  service_name: string
  ssl_enabled: boolean
  health_check_url: string
  health_check_passed: boolean
  error_message: string
  failed_step: string
  recommended_action: string
  deployment_time_seconds: number
  created_at: string
  completed_at: string | null
  rollback_available: boolean
}

interface DeployStep {
  name: string
  display_name: string
  status: string
  message: string
  duration_seconds: number
}

interface DeployLog {
  timestamp: string
  step: string
  message: string
  severity: string
}

const statusColors: Record<string, string> = {
  pending: "bg-gray-500/10 text-gray-400 border-gray-500/30",
  analyzing: "bg-purple-500/10 text-purple-400 border-purple-500/30",
  plan_ready: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  waiting_for_approval: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  connecting: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  preparing_server: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  cloning: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  installing: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  building: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
  configuring: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
  migrating: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  starting: "bg-green-500/10 text-green-400 border-green-500/30",
  health_check: "bg-green-500/10 text-green-400 border-green-500/30",
  verifying: "bg-green-500/10 text-green-400 border-green-500/30",
  deployed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  failed: "bg-red-500/10 text-red-400 border-red-500/30",
  rolling_back: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  rolled_back: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  cancelled: "bg-gray-500/10 text-gray-400 border-gray-500/30",
  waiting_for_input: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
}

const stepStatusIcon: Record<string, string> = {
  pending: "○",
  running: "◉",
  passed: "✓",
  failed: "✗",
  skipped: "–",
}

const stepStatusColor: Record<string, string> = {
  pending: "text-gray-500",
  running: "text-blue-400 animate-pulse",
  passed: "text-green-400",
  failed: "text-red-400",
  skipped: "text-gray-600",
}

export default function VPSDeployPage() {
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [selected, setSelected] = useState<Deployment | null>(null)
  const [steps, setSteps] = useState<DeployStep[]>([])
  const [logs, setLogs] = useState<DeployLog[]>([])
  const [showForm, setShowForm] = useState(false)
  const [deploying, setDeploying] = useState(false)
  const [form, setForm] = useState({
    project_name: "",
    github_repo: "",
    branch: "main",
    domain: "",
    vps_host: "",
    vps_port: "22",
    vps_username: "root",
    vps_private_key: "",
    vps_password: "",
    deploy_mode: "automatic" as "automatic" | "approval",
    env_vars: "",
  })
  const [error, setError] = useState("")
  const pollRef = useRef<NodeJS.Timeout | null>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  const fetchData = async () => {
    try {
      const res = await fetch(`${API}/api/vps-deployments`)
      const data = await res.json()
      setDeployments(data.deployments || [])
    } catch {}
  }

  const fetchDetail = async (id: string) => {
    try {
      const res = await fetch(`${API}/api/vps-deployments/${id}`)
      const data = await res.json()
      if (data.deployment) {
        setSelected(data.deployment)
        setSteps(data.steps || [])
        setLogs(data.logs || [])
      }
    } catch {}
  }

  useEffect(() => {
    fetchData()
    pollRef.current = setInterval(() => {
      fetchData()
      if (selected) fetchDetail(selected.id)
    }, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [selected?.id])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logs.length])

  const submitDeploy = async () => {
    if (!form.project_name || !form.github_repo || !form.vps_host) {
      setError("Project name, GitHub repo, and VPS host are required.")
      return
    }
    setDeploying(true)
    setError("")
    try {
      const envVars: Record<string, string> = {}
      if (form.env_vars) {
        form.env_vars.split("\n").forEach((line) => {
          const [k, ...v] = line.split("=")
          if (k && v.length) envVars[k.trim()] = v.join("=").trim()
        })
      }
      const res = await fetch(`${API}/api/vps-deployments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_name: form.project_name,
          github_repo: form.github_repo,
          branch: form.branch,
          domain: form.domain,
          vps_host: form.vps_host,
          vps_port: parseInt(form.vps_port),
          vps_username: form.vps_username,
          vps_private_key: form.vps_private_key,
          vps_password: form.vps_password,
          deploy_mode: form.deploy_mode,
          env_vars: envVars,
        }),
      })
      const data = await res.json()
      if (data.deployment_id) {
        setShowForm(false)
        setForm({ project_name: "", github_repo: "", branch: "main", domain: "", vps_host: "", vps_port: "22", vps_username: "root", vps_private_key: "", vps_password: "", deploy_mode: "automatic", env_vars: "" })
        setLogs([])
        setSteps([])
        fetchData()
        setSelected({ id: data.deployment_id, project_name: form.project_name, status: data.status, github_repo: form.github_repo, branch: form.branch, domain: form.domain, vps_host: form.vps_host, vps_username: form.vps_username, deploy_mode: form.deploy_mode, deploy_strategy: "", detected_stack: {}, deployment_plan: "", commit_sha: "", service_name: "", ssl_enabled: false, health_check_url: "", health_check_passed: false, error_message: "", failed_step: "", recommended_action: "", deployment_time_seconds: 0, created_at: "", completed_at: null, rollback_available: false })
      } else if (data.error) {
        setError(data.error)
      }
    } catch (e) {
      setError(`Failed: ${e}`)
    }
    setDeploying(false)
  }

  const approveDeploy = async (id: string) => {
    await fetch(`${API}/api/vps-deployments/${id}/approve`, { method: "POST" })
    fetchData()
  }

  const cancelDeploy = async (id: string) => {
    await fetch(`${API}/api/vps-deployments/${id}/cancel`, { method: "POST" })
    fetchData()
  }

  const rollbackDeploy = async (id: string) => {
    await fetch(`${API}/api/vps-deployments/${id}/rollback`, { method: "POST" })
    fetchData()
  }

  const retryDeploy = async (id: string) => {
    await fetch(`${API}/api/vps-deployments/${id}/retry`, { method: "POST" })
    fetchData()
  }

  const deleteDeploy = async (id: string) => {
    await fetch(`${API}/api/vps-deployments/${id}`, { method: "DELETE" })
    if (selected?.id === id) setSelected(null)
    fetchData()
  }

  const activeDeployments = deployments.filter((d) => !["deployed", "failed", "rolled_back", "cancelled"].includes(d.status))
  const completedDeployments = deployments.filter((d) => d.status === "deployed")
  const failedDeployments = deployments.filter((d) => ["failed", "rolled_back"].includes(d.status))

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">VPS Deploy</h1>
            <p className="text-muted-foreground">Deploy web apps to VPS via SSH</p>
          </div>
          <button onClick={() => setShowForm(!showForm)} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
            {showForm ? "Cancel" : "+ New Deployment"}
          </button>
        </div>

        {/* Deploy Form */}
        {showForm && (
          <div className="rounded-xl border border-border bg-card p-6 space-y-4">
            <h3 className="font-semibold text-emerald-400">New VPS Deployment</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted-foreground">Project Name *</label>
                <input value={form.project_name} onChange={(e) => setForm({ ...form, project_name: e.target.value })} placeholder="My SaaS App" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">GitHub Repository *</label>
                <input value={form.github_repo} onChange={(e) => setForm({ ...form, github_repo: e.target.value })} placeholder="https://github.com/user/repo" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Branch</label>
                <input value={form.branch} onChange={(e) => setForm({ ...form, branch: e.target.value })} placeholder="main" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Domain (optional)</label>
                <input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="app.example.com" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <h4 className="text-sm font-medium text-blue-400 mb-3">VPS Connection</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground">Host *</label>
                  <input value={form.vps_host} onChange={(e) => setForm({ ...form, vps_host: e.target.value })} placeholder="server.example.com" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Port</label>
                  <input value={form.vps_port} onChange={(e) => setForm({ ...form, vps_port: e.target.value })} placeholder="22" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Username *</label>
                  <input value={form.vps_username} onChange={(e) => setForm({ ...form, vps_username: e.target.value })} placeholder="root" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                <div>
                  <label className="text-xs text-muted-foreground">SSH Private Key (paste full key)</label>
                  <textarea value={form.vps_private_key} onChange={(e) => setForm({ ...form, vps_private_key: e.target.value })} placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-24 resize-none font-mono text-xs" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Or Password (if no key)</label>
                  <input type="password" value={form.vps_password} onChange={(e) => setForm({ ...form, vps_password: e.target.value })} placeholder="SSH password" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
                  <p className="text-xs text-muted-foreground mt-1">Credentials are encrypted and never shown again.</p>
                </div>
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground">Deploy Mode</label>
                  <div className="flex gap-2 mt-1">
                    <button onClick={() => setForm({ ...form, deploy_mode: "automatic" })} className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium border ${form.deploy_mode === "automatic" ? "bg-emerald-600 text-white border-emerald-500" : "bg-secondary text-muted-foreground border-border"}`}>Automatic</button>
                    <button onClick={() => setForm({ ...form, deploy_mode: "approval" })} className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium border ${form.deploy_mode === "approval" ? "bg-yellow-600 text-white border-yellow-500" : "bg-secondary text-muted-foreground border-border"}`}>Approval Required</button>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Environment Variables (KEY=value, one per line)</label>
                  <textarea value={form.env_vars} onChange={(e) => setForm({ ...form, env_vars: e.target.value })} placeholder={"DATABASE_URL=postgres://...\nSECRET_KEY=..."} className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-20 resize-none font-mono text-xs" />
                </div>
              </div>
            </div>

            {error && <div className="text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/30">{error}</div>}

            <div className="flex justify-end gap-2">
              <button onClick={() => setShowForm(false)} className="rounded-lg bg-secondary px-4 py-2 text-sm">Cancel</button>
              <button onClick={submitDeploy} disabled={deploying} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                {deploying ? "Deploying..." : "Start Deployment"}
              </button>
            </div>
          </div>
        )}

        {/* Stats */}
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Total</p>
            <p className="text-2xl font-bold">{deployments.length}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Active</p>
            <p className="text-2xl font-bold text-blue-400">{activeDeployments.length}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Deployed</p>
            <p className="text-2xl font-bold text-green-400">{completedDeployments.length}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Failed</p>
            <p className="text-2xl font-bold text-red-400">{failedDeployments.length}</p>
          </div>
        </div>

        {/* Active Deployments */}
        {activeDeployments.length > 0 && (
          <div className="rounded-lg border border-border bg-card p-6">
            <h2 className="text-lg font-semibold mb-4 text-blue-400">Active Deployments</h2>
            <div className="space-y-3">
              {activeDeployments.map((d) => (
                <div key={d.id} className="rounded border border-border p-4 bg-blue-500/5 cursor-pointer hover:bg-blue-500/10" onClick={() => setSelected(d)}>
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-medium">{d.project_name}</h4>
                      <p className="text-xs text-muted-foreground">{d.github_repo} ({d.branch})</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`text-xs px-3 py-1 rounded-full border ${statusColors[d.status] || statusColors.pending}`}>{d.status.replace(/_/g, " ")}</span>
                      {d.status === "waiting_for_approval" && (
                        <div className="flex gap-1">
                          <button onClick={(e) => { e.stopPropagation(); approveDeploy(d.id) }} className="text-xs bg-green-500/10 text-green-400 px-2 py-1 rounded hover:bg-green-500/20">Approve</button>
                          <button onClick={(e) => { e.stopPropagation(); cancelDeploy(d.id) }} className="text-xs bg-red-500/10 text-red-400 px-2 py-1 rounded hover:bg-red-500/20">Cancel</button>
                        </div>
                      )}
                      <button onClick={(e) => { e.stopPropagation(); cancelDeploy(d.id) }} className="text-xs bg-red-500/10 text-red-400 px-2 py-1 rounded hover:bg-red-500/20">Stop</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Deployment List */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">All Deployments</h2>
          {deployments.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No deployments yet</p>
              <p className="text-xs text-muted-foreground mt-1">Click "New Deployment" to deploy a project to VPS.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {deployments.map((d) => (
                <div key={d.id} className={`flex items-center justify-between rounded border p-4 cursor-pointer hover:bg-secondary/30 ${selected?.id === d.id ? "border-emerald-500/50 bg-emerald-500/5" : "border-border"}`} onClick={() => setSelected(d)}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <h4 className="font-medium truncate">{d.project_name}</h4>
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${statusColors[d.status] || statusColors.pending}`}>{d.status.replace(/_/g, " ")}</span>
                      {d.domain && <span className="text-xs text-muted-foreground truncate">{d.domain}</span>}
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 truncate">{d.github_repo} ({d.branch}) → {d.vps_host}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    {d.status === "failed" && <button onClick={(e) => { e.stopPropagation(); retryDeploy(d.id) }} className="text-xs bg-blue-500/10 text-blue-400 px-2 py-1 rounded hover:bg-blue-500/20">Retry</button>}
                    {d.rollback_available && (d.status === "failed" || d.status === "deployed") && <button onClick={(e) => { e.stopPropagation(); rollbackDeploy(d.id) }} className="text-xs bg-orange-500/10 text-orange-400 px-2 py-1 rounded hover:bg-orange-500/20">Rollback</button>}
                    {d.status === "waiting_for_approval" && <button onClick={(e) => { e.stopPropagation(); approveDeploy(d.id) }} className="text-xs bg-green-500/10 text-green-400 px-2 py-1 rounded hover:bg-green-500/20">Approve</button>}
                    <button onClick={(e) => { e.stopPropagation(); if (confirm(`Delete deployment "${d.project_name}"?`)) deleteDeploy(d.id) }} className="text-xs bg-red-500/10 text-red-400 px-2 py-1 rounded hover:bg-red-500/20">Delete</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Deployment Detail Panel */}
        {selected && (
          <div className="rounded-lg border border-border bg-card p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold">{selected.project_name}</h2>
                <p className="text-xs text-muted-foreground">{selected.github_repo} → {selected.vps_host}</p>
              </div>
              <button onClick={() => setSelected(null)} className="text-xs text-muted-foreground hover:text-foreground">Close</button>
            </div>

            {/* Steps */}
            {steps.length > 0 && (
              <div>
                <h3 className="text-sm font-medium mb-2">Progress</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {steps.map((s) => (
                    <div key={s.name} className="flex items-center gap-2 text-sm p-2 rounded bg-secondary/30">
                      <span className={stepStatusColor[s.status]}>{stepStatusIcon[s.status]}</span>
                      <span className="truncate">{s.display_name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Detected Stack */}
            {selected.detected_stack && Object.keys(selected.detected_stack).length > 0 && (
              <div>
                <h3 className="text-sm font-medium mb-2">Detected Stack</h3>
                <div className="flex flex-wrap gap-2">
                  {selected.detected_stack.frontend && <span className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-400 border border-blue-500/30">{selected.detected_stack.frontend}</span>}
                  {selected.detected_stack.backend && <span className="text-xs px-2 py-1 rounded bg-green-500/10 text-green-400 border border-green-500/30">{selected.detected_stack.backend}</span>}
                  {selected.detected_stack.database && <span className="text-xs px-2 py-1 rounded bg-orange-500/10 text-orange-400 border border-orange-500/30">{selected.detected_stack.database}</span>}
                  {selected.detected_stack.has_docker && <span className="text-xs px-2 py-1 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">Docker</span>}
                </div>
              </div>
            )}

            {/* Plan */}
            {selected.deployment_plan && (
              <div>
                <h3 className="text-sm font-medium mb-2">Deployment Plan</h3>
                <pre className="text-xs text-muted-foreground bg-secondary/50 rounded-lg p-4 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto">{selected.deployment_plan}</pre>
              </div>
            )}

            {/* Logs */}
            <div>
              <h3 className="text-sm font-medium mb-2">Logs</h3>
              <div className="bg-black/40 rounded-lg p-4 max-h-80 overflow-y-auto font-mono text-xs space-y-1">
                {logs.map((l, i) => (
                  <div key={i} className={`flex gap-2 ${l.severity === "error" ? "text-red-400" : l.severity === "warning" ? "text-yellow-400" : l.severity === "success" ? "text-green-400" : "text-gray-400"}`}>
                    <span className="text-gray-600 shrink-0">{new Date(l.timestamp).toLocaleTimeString()}</span>
                    <span>{l.message}</span>
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            </div>

            {/* Error */}
            {selected.error_message && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                <p className="text-sm text-red-400 font-medium">Error: {selected.error_message}</p>
                {selected.failed_step && <p className="text-xs text-red-400 mt-1">Failed at: {selected.failed_step}</p>}
                {selected.recommended_action && (
                  <div className="mt-3 bg-yellow-500/10 border border-yellow-500/30 rounded p-3">
                    <p className="text-xs text-yellow-400 font-semibold mb-1">How to fix (run on your VPS via SSH):</p>
                    <pre className="text-xs text-yellow-300 whitespace-pre-wrap font-mono">{selected.recommended_action}</pre>
                  </div>
                )}
              </div>
            )}

            {/* Health */}
            {selected.health_check_url && (
              <div className="text-xs text-muted-foreground">
                Health URL: <a href={selected.health_check_url} target="_blank" rel="noopener" className="text-emerald-400 hover:underline">{selected.health_check_url}</a>
                {selected.health_check_passed && <span className="ml-2 text-green-400">✓ Passed</span>}
              </div>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
