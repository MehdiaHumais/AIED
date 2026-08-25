"use client"

import { cn } from "@/lib/utils"

const agents = [
  { id: "hermes", name: "Hermes", role: "Orchestrator", status: "working", department: "Executive" },
  { id: "openclaw", name: "OpenClaw", role: "Software Engineer", status: "idle", department: "Engineering" },
  { id: "product-manager", name: "Product Manager", role: "Product", status: "idle", department: "Product" },
  { id: "software-architect", name: "Software Architect", role: "Architecture", status: "working", department: "Architecture" },
  { id: "backend-engineer", name: "Backend Engineer", role: "Backend", status: "idle", department: "Development" },
  { id: "frontend-engineer", name: "Frontend Engineer", role: "Frontend", status: "idle", department: "Development" },
  { id: "qa-engineer", name: "QA Engineer", role: "Quality", status: "idle", department: "Quality" },
  { id: "security-engineer", name: "Security Engineer", role: "Security", status: "idle", department: "Quality" },
  { id: "ui-designer", name: "UI Designer", role: "UX", status: "idle", department: "UX" },
  { id: "deployment-engineer", name: "Deployment Engineer", role: "DevOps", status: "idle", department: "DevOps" },
  { id: "analytics-agent", name: "Analytics Agent", role: "Intelligence", status: "idle", department: "Intelligence" },
  { id: "documentation-agent", name: "Documentation Agent", role: "Docs", status: "idle", department: "Intelligence" },
]

const statusColors = {
  working: "bg-green-500",
  idle: "bg-yellow-500",
  error: "bg-red-500",
  offline: "bg-gray-500",
}

export function AgentGrid() {
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="text-lg font-semibold mb-4">AI Agents</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="flex items-center gap-3 rounded-lg border border-border p-3 hover:bg-secondary/50 transition-colors cursor-pointer"
          >
            <div className="relative">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <span className="text-sm font-bold text-primary">
                  {agent.name[0]}
                </span>
              </div>
              <div
                className={cn(
                  "absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-card",
                  statusColors[agent.status as keyof typeof statusColors]
                )}
              />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{agent.name}</p>
              <p className="text-xs text-muted-foreground">{agent.role}</p>
            </div>
            <span className="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded">
              {agent.department}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
