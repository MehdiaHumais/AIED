"use client"

const projects = [
  {
    id: "1",
    name: "BritStore",
    codename: "Project Phoenix",
    status: "in_progress",
    progress: 65,
    agents: 8,
    tasks: { total: 42, completed: 27 },
  },
  {
    id: "2",
    name: "BritLedger AI",
    codename: "Project Atlas",
    status: "planning",
    progress: 15,
    agents: 4,
    tasks: { total: 28, completed: 4 },
  },
  {
    id: "3",
    name: "AIED Dashboard",
    codename: "Project Hermes",
    status: "in_progress",
    progress: 40,
    agents: 6,
    tasks: { total: 35, completed: 14 },
  },
]

const statusLabels: Record<string, { label: string; color: string }> = {
  planning: { label: "Planning", color: "bg-yellow-500/10 text-yellow-500" },
  in_progress: { label: "In Progress", color: "bg-blue-500/10 text-blue-500" },
  testing: { label: "Testing", color: "bg-purple-500/10 text-purple-500" },
  deployed: { label: "Deployed", color: "bg-green-500/10 text-green-500" },
}

export function ProjectList() {
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Projects</h2>
        <button className="text-sm text-primary hover:underline">
          View All
        </button>
      </div>
      <div className="space-y-3">
        {projects.map((project) => {
          const status = statusLabels[project.status] || statusLabels.planning
          return (
            <div
              key={project.id}
              className="flex items-center gap-4 rounded-lg border border-border p-4 hover:bg-secondary/50 transition-colors cursor-pointer"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-medium">{project.name}</h3>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${status.color}`}>
                    {status.label}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  {project.codename} &middot; {project.agents} agents &middot;{" "}
                  {project.tasks.completed}/{project.tasks.total} tasks
                </p>
              </div>
              <div className="w-32">
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-muted-foreground">Progress</span>
                  <span>{project.progress}%</span>
                </div>
                <div className="h-2 rounded-full bg-secondary overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all"
                    style={{ width: `${project.progress}%` }}
                  />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
