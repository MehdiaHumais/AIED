"use client"

import { Bot, FolderKanban, CheckCircle, AlertTriangle } from "lucide-react"

const stats = [
  {
    title: "Active Agents",
    value: "30",
    change: "+2 today",
    icon: Bot,
    color: "text-blue-500",
    bg: "bg-blue-500/10",
  },
  {
    title: "Projects",
    value: "5",
    change: "2 in progress",
    icon: FolderKanban,
    color: "text-green-500",
    bg: "bg-green-500/10",
  },
  {
    title: "Tasks Completed",
    value: "147",
    change: "+23 this week",
    icon: CheckCircle,
    color: "text-emerald-500",
    bg: "bg-emerald-500/10",
  },
  {
    title: "Failed Tasks",
    value: "3",
    change: "1 retrying",
    icon: AlertTriangle,
    color: "text-red-500",
    bg: "bg-red-500/10",
  },
]

export function StatsCards() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat) => (
        <div
          key={stat.title}
          className="rounded-lg border border-border bg-card p-6"
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted-foreground">
              {stat.title}
            </p>
            <div className={`rounded-lg p-2 ${stat.bg}`}>
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
            </div>
          </div>
          <div className="mt-2">
            <p className="text-3xl font-bold">{stat.value}</p>
            <p className="text-xs text-muted-foreground">{stat.change}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
