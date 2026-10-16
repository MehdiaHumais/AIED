"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { useAuth } from "@/components/auth-provider"
import { CheckCircle, Loader2, KeyRound, Eye, EyeOff, Plus, Trash2 } from "lucide-react"

export default function SettingsPage() {
  const { user, token, refreshUser, logout } = useAuth()
  const router = useRouter()
  const [name, setName] = useState("")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")

  const [currPw, setCurrPw] = useState("")
  const [newPw, setNewPw] = useState("")
  const [confirmPw, setConfirmPw] = useState("")
  const [showPw, setShowPw] = useState(false)
  const [changingPw, setChangingPw] = useState(false)
  const [pwMsg, setPwMsg] = useState("")
  const [pwType, setPwType] = useState<"ok" | "err">("ok")

  const [keyProviders, setKeyProviders] = useState<{ id: string; label: string }[]>([])
  const [myKeys, setMyKeys] = useState<{ provider: string; label: string; masked_key: string; base_url?: string; model?: string; is_custom?: boolean }[]>([])
  const [keyProvider, setKeyProvider] = useState("openai")
  const [customName, setCustomName] = useState("")
  const [customBaseUrl, setCustomBaseUrl] = useState("")
  const [customModel, setCustomModel] = useState("")
  const [keyValue, setKeyValue] = useState("")
  const [keySaving, setKeySaving] = useState(false)
  const [keyMsg, setKeyMsg] = useState("")
  const [keyErr, setKeyErr] = useState("")
  const [agents, setAgents] = useState<{ id: string; name: string; department?: string; model?: string; default_provider?: string; assigned_provider?: string }[]>([])
  const [agentBusy, setAgentBusy] = useState("")
  const [keyErrors, setKeyErrors] = useState<{ provider: string; message: string; status?: number }[]>([])

  useEffect(() => {
    if (user) setName(user.name || "")
  }, [user])

  const loadKeys = async () => {
    if (!token) return
    try {
      const [pr, kr] = await Promise.all([
        fetch("/api/llm-keys/providers"),
        fetch(`/api/llm-keys?token=${encodeURIComponent(token)}`),
      ])
      const pd = await pr.json()
      const kd = await kr.json()
      if (Array.isArray(pd.providers)) setKeyProviders(pd.providers)
      if (Array.isArray(kd.keys)) setMyKeys(kd.keys)
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    loadKeys()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const isCustom = keyProvider === "__custom__"

  const handleSaveKey = async () => {
    setKeyErr("")
    setKeyMsg("")
    if (!token) { setKeyErr("Not authenticated"); return }
    const provider = isCustom
      ? customName.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "")
      : keyProvider
    if (!provider) { setKeyErr("Provider name is required"); return }
    if (!keyValue.trim()) { setKeyErr("API key is required"); return }
    if (isCustom && !customBaseUrl.trim()) { setKeyErr("Base URL is required for a custom provider"); return }
    setKeySaving(true)
    try {
      const res = await fetch("/api/llm-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          provider,
          api_key: keyValue.trim(),
          base_url: isCustom ? customBaseUrl.trim() : undefined,
          model: isCustom ? customModel.trim() : undefined,
        }),
      })
      const data = await res.json()
      if (data.error) {
        setKeyErr(data.error)
      } else {
        if (Array.isArray(data.keys)) setMyKeys(data.keys)
        setKeyValue("")
        setKeyMsg("Key saved")
        setTimeout(() => setKeyMsg(""), 3000)
      }
    } catch {
      setKeyErr("Failed to save key")
    } finally {
      setKeySaving(false)
    }
  }

  const handleRemoveKey = async (provider: string) => {
    if (!token) return
    setKeyErr("")
    setKeyMsg("")
    try {
      const res = await fetch(`/api/llm-keys/${encodeURIComponent(provider)}?token=${encodeURIComponent(token)}`, {
        method: "DELETE",
      })
      const data = await res.json()
      if (data.error) setKeyErr(data.error)
      else if (Array.isArray(data.keys)) setMyKeys(data.keys)
    } catch {
      setKeyErr("Failed to remove key")
    }
  }

  useEffect(() => {
    if (!token) return
    ;(async () => {
      try {
        const [ar, sr] = await Promise.all([
          fetch(`/api/llm-keys/agents?token=${encodeURIComponent(token)}`),
          fetch(`/api/llm-keys/status?token=${encodeURIComponent(token)}`),
        ])
        const ad = await ar.json()
        const sd = await sr.json()
        if (Array.isArray(ad.agents)) setAgents(ad.agents)
        if (Array.isArray(sd.errors)) setKeyErrors(sd.errors)
      } catch {
        /* ignore */
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const handleAgentProvider = async (agentId: string, provider: string) => {
    if (!token) return
    setAgentBusy(agentId)
    setKeyErr("")
    try {
      const res = await fetch("/api/llm-keys/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, agent_id: agentId, provider }),
      })
      const data = await res.json()
      if (data.error) setKeyErr(data.error)
      else setAgents((prev) => prev.map((a) => (a.id === agentId ? { ...a, assigned_provider: provider } : a)))
    } catch {
      setKeyErr("Failed to update agent routing")
    } finally {
      setAgentBusy("")
    }
  }

  const providersForAgents = (() => {
    const m = new Map<string, { id: string; label: string }>()
    keyProviders.forEach((p) => m.set(p.id, { id: p.id, label: p.label }))
    myKeys.forEach((k) => m.set(k.provider, { id: k.provider, label: k.label }))
    return Array.from(m.values())
  })()

  const handleSave = async () => {
    if (!name.trim() || !token) return
    setSaving(true)
    setError("")
    setSaved(false)
    try {
      const res = await fetch("/api/auth/update-profile", {
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

  const handleChangePassword = async () => {
    setPwMsg("")
    if (!currPw || !newPw) { setPwType("err"); setPwMsg("Current and new passwords are required"); return }
    if (newPw.length < 6) { setPwType("err"); setPwMsg("New password must be at least 6 characters"); return }
    if (newPw !== confirmPw) { setPwType("err"); setPwMsg("New passwords do not match"); return }
    if (!token) { setPwType("err"); setPwMsg("Not authenticated"); return }
    setChangingPw(true)
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, current_password: currPw, new_password: newPw }),
      })
      const data = await res.json()
      if (data.error) { setPwType("err"); setPwMsg(data.error) }
      else {
        setPwType("ok"); setPwMsg("Password changed successfully. Logging you out...")
        setCurrPw(""); setNewPw(""); setConfirmPw("")
        setTimeout(() => {
          logout()
          router.push("/login")
        }, 1200)
      }
    } catch {
      setPwType("err"); setPwMsg("Failed to change password")
    } finally {
      setChangingPw(false)
    }
  }

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-2xl">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground">Configure your profile and AIED</p>
        </div>

        {keyErrors.length > 0 && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm">
            <div className="font-medium text-red-500">Your API keys had recent failures</div>
            <ul className="mt-1 list-disc pl-5 text-red-400 space-y-0.5">
              {keyErrors.map((e, i) => (
                <li key={i}>{e.message}</li>
              ))}
            </ul>
          </div>
        )}

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
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-orange-500" /> Change Password
          </h2>
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="text-sm font-medium">Current Password</label>
                <input
                  type="password"
                  value={currPw}
                  onChange={(e) => setCurrPw(e.target.value)}
                  placeholder="Current password"
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-orange-500"
                />
              </div>
              <div className="relative">
                <label className="text-sm font-medium">New Password</label>
                <input
                  type={showPw ? "text" : "password"}
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                  placeholder="New password"
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 pr-9 text-sm outline-none focus:ring-1 focus:ring-orange-500"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(s => !s)}
                  className="absolute right-2 top-7 text-muted-foreground hover:text-foreground transition-colors"
                  aria-label={showPw ? "Hide new password" : "Show new password"}
                >
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <div className="relative">
                <label className="text-sm font-medium">Confirm New Password</label>
                <input
                  type={showPw ? "text" : "password"}
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  placeholder="Confirm new password"
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 pr-9 text-sm outline-none focus:ring-1 focus:ring-orange-500"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(s => !s)}
                  className="absolute right-2 top-7 text-muted-foreground hover:text-foreground transition-colors"
                  aria-label={showPw ? "Hide confirm password" : "Show confirm password"}
                >
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={handleChangePassword}
                disabled={changingPw}
                className="flex items-center gap-1.5 rounded-lg bg-orange-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50 transition-colors"
              >
                {changingPw ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                Change Password
              </button>
              {pwMsg && (
                <span className={pwType === "ok" ? "text-sm text-green-500" : "text-sm text-red-500"}>{pwMsg}</span>
              )}
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
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-orange-500" /> API Keys (Bring Your Own)
          </h2>
          <p className="text-sm text-muted-foreground">
            Add your own provider keys. When set, all AI work you start uses your key first and falls
            back to the platform key if it fails.
          </p>

          {myKeys.length > 0 && (
            <div className="space-y-2">
              {myKeys.map((k) => (
                <div
                  key={k.provider}
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <div className="font-medium truncate">{k.label}</div>
                    <div className="font-mono text-xs text-muted-foreground truncate">{k.masked_key}</div>
                  </div>
                  <button
                    onClick={() => handleRemoveKey(k.provider)}
                    className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs text-red-500 hover:bg-red-500/10 transition-colors shrink-0"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Remove
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="space-y-3 pt-1">
            <div>
              <label className="text-sm font-medium">Provider</label>
              <select
                value={keyProvider}
                onChange={(e) => { setKeyProvider(e.target.value); setKeyErr(""); setKeyMsg("") }}
                className="mt-1 w-full max-w-sm rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-orange-500"
              >
                {keyProviders.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
                <option value="__custom__">Custom (OpenAI-compatible)</option>
              </select>
            </div>

            {isCustom && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="text-sm font-medium">Name</label>
                  <input
                    type="text"
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                    placeholder="e.g. my-llm"
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-orange-500"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Base URL</label>
                  <input
                    type="text"
                    value={customBaseUrl}
                    onChange={(e) => setCustomBaseUrl(e.target.value)}
                    placeholder="https://host/v1"
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-orange-500"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Model</label>
                  <input
                    type="text"
                    value={customModel}
                    onChange={(e) => setCustomModel(e.target.value)}
                    placeholder="model name"
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-orange-500"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="text-sm font-medium">API Key</label>
              <input
                type="password"
                value={keyValue}
                onChange={(e) => setKeyValue(e.target.value)}
                placeholder="sk-..."
                className="mt-1 w-full max-w-sm rounded-md border border-border bg-background px-3 py-1.5 text-sm font-mono outline-none focus:ring-1 focus:ring-orange-500"
              />
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={handleSaveKey}
                disabled={keySaving || !keyValue.trim()}
                className="flex items-center gap-1.5 rounded-lg bg-orange-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50 transition-colors"
              >
                {keySaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                Save Key
              </button>
              {keyMsg && <span className="text-sm text-green-500">{keyMsg}</span>}
              {keyErr && <span className="text-sm text-red-500">{keyErr}</span>}
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-6 space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-orange-500" /> Agent Model Routing
          </h2>
          <p className="text-sm text-muted-foreground">
            Choose which of your saved providers each agent should use. Leave on{" "}
            <span className="font-medium">Default</span> to use the platform routing.
          </p>
          <div className="space-y-2 max-h-96 overflow-auto pr-1">
            {agents.length === 0 && (
              <div className="text-sm text-muted-foreground">No agents found.</div>
            )}
            {agents.map((a) => {
              const hasAssignedKey = a.assigned_provider ? myKeys.some((k) => k.provider === a.assigned_provider) : true
              return (
                <div
                  key={a.id}
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <div className="font-medium truncate">{a.name}</div>
                    <div className="text-xs text-muted-foreground truncate">
                      {a.department ? `${a.department} · ` : ""}default: {a.default_provider || "auto"}
                      {a.model ? ` (${a.model})` : ""}
                    </div>
                  </div>
                  <select
                    value={a.assigned_provider || ""}
                    disabled={agentBusy === a.id}
                    onChange={(e) => handleAgentProvider(a.id, e.target.value)}
                    className={`w-44 shrink-0 rounded-md border bg-background px-2 py-1.5 text-sm outline-none focus:ring-1 focus:ring-orange-500 ${hasAssignedKey ? "border-border" : "border-red-500/60"}`}
                  >
                    <option value="">Default</option>
                    {providersForAgents.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                        {myKeys.some((k) => k.provider === p.id) ? " ✓" : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )
            })}
          </div>
          {myKeys.length === 0 && agents.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Add a provider key above first — pinned agents can only use providers you have keys for.
            </p>
          )}
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
