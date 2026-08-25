"use client"

import { useEffect, useState, useRef } from "react"
import { useRouter } from "next/navigation"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { useAuth } from "@/components/auth-provider"

interface Notification {
  title: string
  message: string
  task_id: string
  type: string
  timestamp: string
  read: boolean
}

const typeColors: Record<string, string> = {
  success: "bg-green-500/10 text-green-400 border-green-500/20",
  error: "bg-red-500/10 text-red-400 border-red-500/20",
  warning: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  info: "bg-blue-500/10 text-blue-400 border-blue-500/20",
}

const typeDot: Record<string, string> = {
  success: "bg-green-500",
  error: "bg-red-500",
  warning: "bg-yellow-500",
  info: "bg-blue-500",
}

export default function HistoryPage() {
  const router = useRouter()
  const { user } = useAuth()
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  const fetchNotifs = () => {
    const uid = user?.id ? `?user_id=${user.id}` : ""
    fetch(`http://127.0.0.1:8001/api/notifications${uid}`)
      .then((r) => r.json())
      .then((d) => {
        setNotifications(d.notifications || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }

  useEffect(() => {
    if (!user) return
    fetchNotifs()
    pollRef.current = setInterval(fetchNotifs, 5000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [user?.id])

  const clearAll = () => {
    fetch("http://127.0.0.1:8001/api/notifications", { method: "DELETE" })
      .then(() => setNotifications([]))
      .catch(() => {})
  }

  const markRead = (idx: number) => {
    fetch(`http://127.0.0.1:8001/api/notifications/${idx}/read`, { method: "POST" })
      .then(() => fetchNotifs())
      .catch(() => {})
  }

  const navigateToTask = (taskId: string) => {
    if (taskId) {
      router.push("/monitor?task=" + taskId)
    }
  }

  const sorted = [...notifications].reverse()

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Notification History</h1>
            <p className="text-muted-foreground">
              {notifications.length} total | {notifications.filter((n) => !n.read).length} unread
            </p>
          </div>
          {notifications.length > 0 && (
            <button
              onClick={clearAll}
              className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/20 transition-colors"
            >
              Clear All
            </button>
          )}
        </div>

        {loading ? (
          <div className="rounded-lg border border-border bg-card p-12 text-center">
            <p className="text-muted-foreground">Loading notifications...</p>
          </div>
        ) : notifications.length === 0 ? (
          <div className="rounded-lg border border-border bg-card p-12 text-center">
            <p className="text-muted-foreground text-lg">No notifications yet</p>
            <p className="text-sm text-muted-foreground mt-1">Activity from your projects will appear here</p>
          </div>
        ) : (
          <div className="space-y-2">
            {sorted.map((n, i) => {
              const realIdx = notifications.length - 1 - i
              return (
                <div
                  key={i}
                  className={
                    "rounded-lg border border-border bg-card p-4 transition-colors " +
                    (!n.read ? "bg-secondary/20" : "")
                  }
                >
                  <div className="flex items-start gap-3">
                    <span className={"mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-full " + (typeDot[n.type] || "bg-blue-500")} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold">{n.title}</p>
                        <span className={"shrink-0 rounded border px-1.5 py-0.5 text-[10px] " + (typeColors[n.type] || typeColors.info)}>
                          {n.type}
                        </span>
                        {!n.read && (
                          <span className="shrink-0 rounded bg-primary/20 px-1.5 py-0.5 text-[10px] text-primary">
                            NEW
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{n.message}</p>
                      <div className="mt-2 flex items-center gap-3">
                        <p className="text-[10px] text-muted-foreground">
                          {n.timestamp ? new Date(n.timestamp).toLocaleString() : ""}
                        </p>
                        {n.task_id && (
                          <button
                            onClick={() => navigateToTask(n.task_id)}
                            className="text-[10px] text-primary hover:underline"
                          >
                            View in Monitor
                          </button>
                        )}
                        {!n.read && (
                          <button
                            onClick={() => markRead(realIdx)}
                            className="text-[10px] text-muted-foreground hover:text-foreground"
                          >
                            Mark read
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
