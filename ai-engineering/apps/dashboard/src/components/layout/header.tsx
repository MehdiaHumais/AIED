"use client"

import { Bell, Search, X, Sun, Moon, LogOut, Shield } from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect, useState, useRef } from "react"
import { useTheme } from "@/components/theme-provider"
import { useAuth } from "@/components/auth-provider"

interface Notification {
  title: string
  message: string
  task_id: string
  type: string
  timestamp: string
  read: boolean
}

export function Header() {
  const router = useRouter()
  const { theme, toggle } = useTheme()
  const { user, logout } = useAuth()
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [showNotifs, setShowNotifs] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  const fetchNotifs = () => {
    const uid = user?.id ? `?user_id=${user.id}` : ""
    fetch(`http://127.0.0.1:8001/api/notifications${uid}`)
      .then((r) => r.json())
      .then((d) => {
        const incoming = d.notifications || []
        setNotifications(prev => {
          if (JSON.stringify(prev) === JSON.stringify(incoming)) return prev
          return incoming
        })
      })
      .catch(() => {})
  }

  useEffect(() => {
    if (!user) return
    fetchNotifs()
    pollRef.current = setInterval(fetchNotifs, 5000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [user?.id])

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifs(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  const unreadCount = notifications.filter((n) => !n.read).length

  const clearAllNotifications = () => {
    fetch("http://127.0.0.1:8001/api/notifications", { method: "DELETE" })
      .then(() => setNotifications([]))
      .catch(() => {})
  }

  const typeColor = (t: string) => {
    if (t === "success") return "bg-green-500/10 text-green-400 border-green-500/20"
    if (t === "error") return "bg-red-500/10 text-red-400 border-red-500/20"
    if (t === "warning") return "bg-yellow-500/10 text-yellow-400 border-yellow-500/20"
    return "bg-blue-500/10 text-blue-400 border-blue-500/20"
  }

  const handleNotifClick = (n: Notification, idx: number) => {
    fetch(`http://127.0.0.1:8001/api/notifications/${idx}/read`, { method: "POST" })
    if (n.task_id) {
      router.push(`/monitor?task=${n.task_id}`)
    }
    setShowNotifs(false)
  }

  const handleLogout = () => {
    logout()
    router.push("/login")
  }

  const userInitial = user?.name?.[0]?.toUpperCase() || "U"

  return (
    <header className="flex h-16 items-center justify-between border-b border-border px-6">
      <div className="flex items-center gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search projects, tasks, agents..."
            className="h-9 w-96 rounded-lg border border-border bg-background pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="relative" ref={notifRef}>
          <button onClick={() => setShowNotifs(!showNotifs)} className="relative rounded-lg p-2 hover:bg-secondary">
            <Bell className="h-5 w-5" />
            {unreadCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] text-white">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>

          {showNotifs && (
            <div className="absolute right-0 top-full z-50 mt-2 w-96 max-h-[500px] overflow-y-auto rounded-lg border border-border bg-background shadow-xl">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <span className="text-sm font-semibold text-foreground">Notifications</span>
                <div className="flex items-center gap-2">
                  {notifications.length > 0 && (
                    <button onClick={clearAllNotifications} className="text-xs text-red-400 hover:text-red-300">
                      Clear All
                    </button>
                  )}
                  <button onClick={() => setShowNotifs(false)} className="text-muted-foreground hover:text-foreground">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {notifications.length === 0 ? (
                <p className="p-4 text-center text-xs text-muted-foreground">No notifications yet</p>
              ) : (
                <div className="divide-y divide-border">
                  {notifications.slice().reverse().map((n, i) => (
                    <button
                      key={i}
                      onClick={() => handleNotifClick(n, notifications.length - 1 - i)}
                      className={`w-full text-left px-4 py-3 hover:bg-secondary/50 transition-colors ${!n.read ? "bg-secondary/20" : ""}`}
                    >
                      <div className="flex items-start gap-2">
                        <span className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${n.type === "success" ? "bg-green-500" : n.type === "error" ? "bg-red-500" : n.type === "warning" ? "bg-yellow-500" : "bg-blue-500"}`} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="text-xs font-semibold truncate text-foreground">{n.title}</p>
                            <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${typeColor(n.type)}`}>{n.type}</span>
                          </div>
                          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{n.message}</p>
                          <p className="mt-1 text-[10px] text-muted-foreground">{n.timestamp ? new Date(n.timestamp).toLocaleTimeString() : ""}</p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <button onClick={toggle} className="rounded-lg p-2 hover:bg-secondary transition-colors" title="Toggle theme">
          {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
        {user?.is_admin && (
          <button onClick={() => router.push("/admin")} className="rounded-lg p-2 hover:bg-secondary transition-colors" title="Admin Dashboard">
            <Shield className="h-5 w-5" />
          </button>
        )}
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
            <span className="text-xs font-medium text-primary">{userInitial}</span>
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">{user?.name || "User"}</p>
            <p className="text-xs text-muted-foreground">{user?.is_admin ? "Admin" : user?.company_name || "Member"}</p>
          </div>
          <button onClick={handleLogout} className="ml-2 rounded-lg p-1.5 hover:bg-red-500/10 text-muted-foreground hover:text-red-400 transition-colors" title="Logout">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  )
}
