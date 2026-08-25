"use client"

import { useState, useEffect } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { useAuth } from "@/components/auth-provider"
import { CheckCircle, Loader2 } from "lucide-react"

export default function SettingsPage() {
  const { user, token, refreshUser } = useAuth()
  const [name, setName] = useState("")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (user) setName(user.name || "")
  }, [user])

  const handleSave = async () => {
    if (!name.trim() || !token) return
    setSaving(true)
    setError("")
    setSaved(false)
    try {
      const res = await fetch("http://127.0.0.1:8001/api/auth/update-profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, name: name.trim() }),
      })
      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else if (data.user) {
        await refreshUser()
        setSaved(true)
        setTimeout(() => setSaved(false), 3000)
      }
    } catch {
      setError("Failed to update name")
    } finally {
      setSaving(false)
    }
  }

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-2xl">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground">Configure your profile and AIED</p>
        </div>

        <div className="rounded-lg border border-border bg-card p-6 space-y-4">
          <h2 className="text-lg font-semibold">Profile</h2>
          <div className="space-y-3">
            <div className="text-sm">
              <span className="text-muted-foreground">Email:</span>
              <span className="ml-2 font-mono">{user?.email}</span>
            </div>
            <div className="text-sm">
              <span className="text-muted-foreground">Role:</span>
              <span className="ml-2 font-mono">{user?.is_admin ? "Admin" : "Member"}</span>
            </div>
            <div className="flex items-center gap-3 pt-2">
              <div className="space-y-1 flex-1">
                <label className="text-sm font-medium">Display Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  className="max-w-sm w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-orange-500"
                />
              </div>
              <div className="flex items-center gap-2 pt-5">
                <button
                  onClick={handleSave}
                  disabled={saving || !name.trim() || name.trim() === user?.name}
                  className="flex items-center gap-1.5 rounded-lg bg-orange-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50 transition-colors"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                  Save
                </button>
                {saved && <span className="text-sm text-green-500">Saved!</span>}
                {error && <span className="text-sm text-red-500">{error}</span>}
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-6 space-y-4">
          <h2 className="text-lg font-semibold">LLM Configuration</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Default LLM:</span>
              <span className="ml-2 font-mono">deepseek</span>
            </div>
            <div>
              <span className="text-muted-foreground">Fallback LLM:</span>
              <span className="ml-2 font-mono">openrouter</span>
            </div>
            <div>
              <span className="text-muted-foreground">GLM Provider:</span>
              <span className="ml-2 font-mono">openrouter</span>
            </div>
            <div>
              <span className="text-muted-foreground">MiniMax Provider:</span>
              <span className="ml-2 font-mono">openrouter</span>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-6 space-y-4">
          <h2 className="text-lg font-semibold">Infrastructure</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">PostgreSQL:</span>
              <span className="ml-2 font-mono">Neon</span>
            </div>
            <div>
              <span className="text-muted-foreground">Redis:</span>
              <span className="ml-2 font-mono">Upstash</span>
            </div>
            <div>
              <span className="text-muted-foreground">Qdrant:</span>
              <span className="ml-2 font-mono">Qdrant Cloud</span>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  )
}
