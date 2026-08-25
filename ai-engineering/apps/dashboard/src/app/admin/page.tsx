"use client"

import { useEffect, useState } from "react"
import { useAuth } from "@/components/auth-provider"
import { useRouter } from "next/navigation"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { CheckCircle, XCircle, Clock, Users, Trash2, RefreshCw, Shield } from "lucide-react"

interface PendingUser {
  id: string
  name: string
  email: string
  company_name: string
  company_role: string
  company_size: string
  company_website: string
  status: string
  created_at: string
}

export default function AdminPage() {
  const { user } = useAuth()
  const router = useRouter()
  const [pendingUsers, setPendingUsers] = useState<PendingUser[]>([])
  const [allUsers, setAllUsers] = useState<PendingUser[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [tab, setTab] = useState<"pending" | "all">("pending")

  useEffect(() => {
    if (!loading && (!user || !user.is_admin)) {
      router.replace("/")
    }
  }, [user, loading])

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const [pendingRes, allRes] = await Promise.all([
        fetch("http://127.0.0.1:8001/api/auth/pending-users"),
        fetch("http://127.0.0.1:8001/api/auth/all-users"),
      ])
      const pendingData = await pendingRes.json()
      const allData = await allRes.json()
      setPendingUsers(pendingData.users || [])
      setAllUsers(allData.users || [])
    } catch {}
    setLoading(false)
  }

  useEffect(() => {
    if (user?.is_admin) fetchUsers()
  }, [user])

  const approveUser = async (userId: string) => {
    setActionLoading(userId)
    try {
      await fetch(`http://127.0.0.1:8001/api/auth/approve/${userId}`, { method: "POST" })
      await fetchUsers()
    } catch {}
    setActionLoading(null)
  }

  const rejectUser = async (userId: string) => {
    setActionLoading(userId)
    try {
      await fetch(`http://127.0.0.1:8001/api/auth/reject/${userId}`, { method: "POST" })
      await fetchUsers()
    } catch {}
    setActionLoading(null)
  }

  const deleteUser = async (userId: string) => {
    if (!confirm("Delete this user permanently?")) return
    setActionLoading(userId)
    try {
      await fetch(`http://127.0.0.1:8001/api/auth/delete/${userId}`, { method: "POST" })
      await fetchUsers()
    } catch {}
    setActionLoading(null)
  }

  const statusBadge = (s: string) => {
    if (s === "approved") return "bg-green-500/10 text-green-400"
    if (s === "rejected") return "bg-red-500/10 text-red-400"
    return "bg-yellow-500/10 text-yellow-400"
  }

  const displayUsers = tab === "pending" ? pendingUsers : allUsers

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted-foreground">Loading...</div>
        </div>
      </DashboardLayout>
    )
  }

  if (!user?.is_admin) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-red-400">Access denied. Admin only.</div>
        </div>
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout>
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <Shield className="h-6 w-6 text-orange-400" /> Admin Dashboard
            </h1>
            <p className="text-sm text-muted-foreground">Manage user access</p>
          </div>
          <button onClick={fetchUsers} className="flex items-center gap-2 rounded-lg bg-secondary px-3 py-1.5 text-sm hover:bg-secondary/80 transition-colors">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>

        {/* Stats */}
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-border bg-card p-3 flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-yellow-500/10 flex items-center justify-center">
              <Clock className="h-4 w-4 text-yellow-400" />
            </div>
            <div>
              <p className="text-xl font-bold text-yellow-400">{pendingUsers.length}</p>
              <p className="text-xs text-muted-foreground">Pending</p>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-card p-3 flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-green-500/10 flex items-center justify-center">
              <CheckCircle className="h-4 w-4 text-green-400" />
            </div>
            <div>
              <p className="text-xl font-bold text-green-400">{allUsers.filter(u => u.status === "approved").length}</p>
              <p className="text-xs text-muted-foreground">Approved</p>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-card p-3 flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-orange-500/10 flex items-center justify-center">
              <Users className="h-4 w-4 text-orange-400" />
            </div>
            <div>
              <p className="text-xl font-bold text-orange-400">{allUsers.length}</p>
              <p className="text-xs text-muted-foreground">Total</p>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 border-b border-border">
          <button
            onClick={() => setTab("pending")}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${tab === "pending" ? "border-orange-500 text-orange-400" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            Pending ({pendingUsers.length})
          </button>
          <button
            onClick={() => setTab("all")}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${tab === "all" ? "border-orange-500 text-orange-400" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            All Users ({allUsers.length})
          </button>
        </div>

        {/* User List - Compact Rows */}
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          {displayUsers.length === 0 ? (
            <div className="text-center py-10">
              <Users className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">
                {tab === "pending" ? "No pending requests" : "No users yet"}
              </p>
            </div>
          ) : (
            displayUsers.map((u) => (
              <div
                key={u.id}
                className="flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-b-0 hover:bg-orange-500/5 transition-colors"
              >
                {/* Avatar */}
                <div className="h-8 w-8 rounded-full bg-orange-500/10 flex items-center justify-center shrink-0">
                  <span className="text-xs font-bold text-orange-400">{u.name?.[0]?.toUpperCase() || "?"}</span>
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground truncate">{u.name}</span>
                    <span className={`text-[10px] px-1.5 py-0 rounded-full ${statusBadge(u.status)}`}>
                      {u.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="truncate">{u.email}</span>
                    {u.company_name && <span className="truncate hidden sm:inline">{u.company_name}</span>}
                    <span className="hidden md:inline">{new Date(u.created_at).toLocaleDateString()}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {u.status === "pending" && (
                    <>
                      <button
                        onClick={() => approveUser(u.id)}
                        disabled={actionLoading === u.id}
                        className="flex items-center gap-1 rounded-md bg-green-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
                      >
                        <CheckCircle className="h-3 w-3" /> Approve
                      </button>
                      <button
                        onClick={() => rejectUser(u.id)}
                        disabled={actionLoading === u.id}
                        className="flex items-center gap-1 rounded-md bg-red-600/20 text-red-400 px-2.5 py-1 text-xs font-medium hover:bg-red-600/30 border border-red-500/30 disabled:opacity-50 transition-colors"
                      >
                        <XCircle className="h-3 w-3" /> Reject
                      </button>
                    </>
                  )}
                  {u.status !== "pending" && u.id !== user?.id && (
                    <button
                      onClick={() => deleteUser(u.id)}
                      disabled={actionLoading === u.id}
                      className="flex items-center gap-1 rounded-md bg-red-600/10 text-red-400 px-2.5 py-1 text-xs font-medium hover:bg-red-600/20 border border-red-500/20 disabled:opacity-50 transition-colors"
                    >
                      <Trash2 className="h-3 w-3" /> Delete
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </DashboardLayout>
  )
}
