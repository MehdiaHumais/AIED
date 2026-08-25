"use client"

const tasks = [
  { id: "1", title: "Implement auth flow", agent: "OpenClaw", priority: "high", status: "in_progress" },
  { id: "2", title: "Design API schema", agent: "API Architect", priority: "medium", status: "completed" },
  { id: "3", title: "Setup CI/CD pipeline", agent: "Build Engineer", priority: "high", status: "pending" },
  { id: "4", title: "Write unit tests", agent: "QA Engineer", priority: "medium", status: "pending" },
  { id: "5", title: "Security audit", agent: "Security Engineer", priority: "critical", status: "pending" },
]

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
}

export function TaskQueue() {
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Task Queue</h2>
        <span className="text-xs text-muted-foreground">
          {tasks.filter((t) => t.status === "pending").length} pending
        </span>
      </div>
      <div className="space-y-2">
        {tasks.map((task) => (
          <div
            key={task.id}
            className="flex items-center gap-3 rounded-lg border border-border p-3 hover:bg-secondary/50 transition-colors"
          >
            <span className="text-lg">{statusIcons[task.status]}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{task.title}</p>
              <p className="text-xs text-muted-foreground">{task.agent}</p>
            </div>
            <span className={`text-xs px-2 py-0.5 rounded-full ${priorityColors[task.priority]}`}>
              {task.priority}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
