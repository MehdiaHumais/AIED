"use client"

import { useEffect, useState, useRef } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { useAuth } from "@/components/auth-provider"

interface DashboardData {
  total_agents: number
  active_agents: number
  total_projects: number
  active_projects: number
  total_tasks: number
  pending_tasks: number
  completed_tasks: number
  failed_tasks: number
}

interface Agent {
  id: string
  name: string
  role: string
  department: string
  model: string
  status: string
}

interface Task {
  id: string
  title: string
  status: string
  priority: string
  assigned_to: string | null
}

interface HelperActivity {
  task_id: string
  task_title: string
  helper_name: string
  target_name: string
  message: string
  timestamp: string
}

const statusColors: Record<string, string> = {
  working: "bg-green-500",
  idle: "bg-yellow-500",
  error: "bg-red-500",
  offline: "bg-gray-500",
}

const priorityColors: Record<string, string> = {
  low: "bg-gray-500/10 text-gray-500",
  medium: "bg-blue-500/10 text-blue-500",
  high: "bg-orange-500/10 text-orange-500",
  critical: "bg-red-500/10 text-red-500",
}

const statusIcons: Record<string, string> = {
  pending: "○",
  in_progress: "◉",
  completed: "●",
  failed: "✕",
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [helperActivities, setHelperActivities] = useState<HelperActivity[]>([])
  const [loading, setLoading] = useState(true)
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  const fetchData = () => {
    const uid = user?.id ? `?user_id=${user.id}` : ""
    Promise.all([
      fetch(`http://127.0.0.1:8001/api/dashboard${uid}`).then((r) => r.json()),
      fetch("http://127.0.0.1:8001/api/agents").then((r) => r.json()),
      fetch("http://127.0.0.1:8001/api/tasks").then((r) => r.json()),
      fetch(`http://127.0.0.1:8001/api/helper-activity${uid}`).then((r) => r.json()).catch(() => ({ entries: [] })),
    ])
      .then(([dashData, agentData, taskData, helperData]) => {
        setDashboard(dashData)
        setAgents(agentData.agents || [])
        setTasks(taskData.tasks || [])
        setHelperActivities(helperData.entries || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }

  useEffect(() => { if (user) fetchData() }, [user?.id])
  useEffect(() => {
    if (!user) return
    pollRef.current = setInterval(() => {
      const uid = user?.id ? `?user_id=${user.id}` : ""
      Promise.all([
        fetch(`http://127.0.0.1:8001/api/dashboard${uid}`).then((r) => r.json()).catch(() => null),
        fetch("http://127.0.0.1:8001/api/agents").then((r) => r.json()).catch(() => null),
        fetch("http://127.0.0.1:8001/api/tasks").then((r) => r.json()).catch(() => null),
        fetch(`http://127.0.0.1:8001/api/helper-activity${uid}`).then((r) => r.json()).catch(() => ({ entries: [] })),
      ])
        .then(([dashData, agentData, taskData, helperData]) => {
          if (dashData) setDashboard(dashData)
          if (agentData && agentData.agents) setAgents(agentData.agents)
          if (taskData && taskData.tasks) setTasks(taskData.tasks)
          if (helperData && helperData.entries) setHelperActivities(helperData.entries)
        })
        .catch(() => {})
    }, 5000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [user?.id])

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading dashboard...</p>
        </div>
      </DashboardLayout>
    )
  }

  if (!dashboard) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <p className="text-xl font-semibold mb-2">API Server Not Running</p>
            <p className="text-muted-foreground">
              Start the API: <code className="bg-secondary px-1 rounded">py -m apps.api.main</code>
            </p>
          </div>
        </div>
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Britsync AI Company</h1>
          <p className="text-muted-foreground">AI Engineering Department - {dashboard.total_agents} Agents</p>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Active Agents</p>
            <p className="text-3xl font-bold mt-1">{dashboard.active_agents} / {dashboard.total_agents}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Projects</p>
            <p className="text-3xl font-bold mt-1">{dashboard.active_projects}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Completed Tasks</p>
            <p className="text-3xl font-bold mt-1 text-green-500">{dashboard.completed_tasks}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Pending Tasks</p>
            <p className="text-3xl font-bold mt-1 text-yellow-500">{dashboard.pending_tasks}</p>
          </div>
        </div>

        {(["Executive Command", "Product Strategy", "Engineering & Platform", "AI Workforce Operations", "Design & Brand", "Quality & Security", "DevOps & Deployment"]).map((dept) => {
          const deptAgents = agents.filter((a) => a.department === dept)
          if (deptAgents.length === 0) return null
          const deptColors: Record<string, string> = {
            "Executive Command": "border-yellow-500/30 bg-yellow-500/5",
            "Product Strategy": "border-purple-500/30 bg-purple-500/5",
            "Engineering & Platform": "border-blue-500/30 bg-blue-500/5",
            "AI Workforce Operations": "border-cyan-500/30 bg-cyan-500/5",
            "Design & Brand": "border-pink-500/30 bg-pink-500/5",
            "Quality & Security": "border-green-500/30 bg-green-500/5",
            "DevOps & Deployment": "border-orange-500/30 bg-orange-500/5",
          }
          const deptTextColors: Record<string, string> = {
            "Executive Command": "text-yellow-400",
            "Product Strategy": "text-purple-400",
            "Engineering & Platform": "text-blue-400",
            "AI Workforce Operations": "text-cyan-400",
            "Design & Brand": "text-pink-400",
            "Quality & Security": "text-green-400",
            "DevOps & Deployment": "text-orange-400",
          }
          return (
            <div key={dept} className={`rounded-lg border ${deptColors[dept] || "border-border bg-card"} p-4`}>
              <h2 className={`text-sm font-bold uppercase tracking-wider mb-3 ${deptTextColors[dept] || "text-foreground"}`}>
                {dept} ({deptAgents.length})
              </h2>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {deptAgents.map((agent) => (
                  <div key={agent.id} className="flex items-center gap-3 rounded border border-border/50 bg-background/50 p-2">
                    <div className="relative">
                      <div className="h-8 w-8 rounded bg-primary/10 flex items-center justify-center">
                        <span className="text-xs font-bold text-primary">{agent.name[0]}</span>
                      </div>
                      <div className={`absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-card ${statusColors[agent.status] || "bg-gray-500"}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate">{agent.name}</p>
                      <p className="text-xs text-muted-foreground truncate">{agent.role}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}

        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">Recent Tasks ({tasks.length})</h2>
          {tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tasks yet. Create a project and start building.</p>
          ) : (
            <div className="space-y-2">
              {tasks.slice(0, 10).map((task) => (
                <div key={task.id} className="flex items-center gap-2 rounded border border-border p-2">
                  <span>{statusIcons[task.status] || "○"}</span>
                  <span className="text-xs flex-1 truncate">{task.title}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${priorityColors[task.priority] || ""}`}>
                    {task.priority}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-purple-500/30 bg-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <span className="text-purple-400">✦</span>
              Helper Guidance Feed
            </h2>
            <span className="text-xs text-muted-foreground bg-purple-500/10 text-purple-400 px-2 py-1 rounded">
              {helperActivities.length} intervention{helperActivities.length === 1 ? "" : "s"}
            </span>
          </div>
          {helperActivities.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No helper interventions yet. When a core agent gets stuck on a confusing error, its helper will diagnose the root cause and appear here.
            </p>
          ) : (
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {helperActivities.slice(0, 20).map((entry, i) => {
                const rootCauseMatch = entry.message.match(/\*\*Most Likely Root Cause:\*\*\s*([^\n]+)/i) || entry.message.match(/Most Likely Root Cause:\s*([^\n]+)/i)
                const rootCause = rootCauseMatch ? rootCauseMatch[1].trim() : ""
                return (
                  <div key={i} className="rounded-lg border border-border bg-background/50 p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-purple-400">{entry.helper_name}</span>
                      <span className="text-xs text-muted-foreground">→</span>
                      <span className="text-xs font-semibold">{entry.target_name}</span>
                      <span className="text-[10px] text-muted-foreground ml-auto">
                        {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : ""}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{entry.task_title}</p>
                    <p className="text-xs mt-1.5">
                      {rootCause ? (
                        <>
                          <span className="text-[10px] font-bold text-purple-400 uppercase">Root cause: </span>
                          {rootCause}
                        </>
                      ) : (
                        "Provided step-by-step guidance"
                      )}
                    </p>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  )
}
