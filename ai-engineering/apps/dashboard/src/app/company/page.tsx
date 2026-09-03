"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import { useAuth } from "@/components/auth-provider"
import {
  Building2,
  FolderOpen,
  Plus,
  Loader2,
  Save,
  Trash2,
  Edit3,
  ExternalLink,
  Search,
  X,
  CheckCircle2,
  AlertCircle,
  Folder,
  Globe,
  Target,
  Users,
  Calendar,
  Mail,
  Phone,
  MapPin,
  Link2,
  Briefcase,
  ChevronRight,
  Sparkles,
  Server,
  Lock,
  KeyRound,
  Eye,
  EyeOff,
} from "lucide-react"
import { cn } from "@/lib/utils"

const API = "http://127.0.0.1:8001"

interface CompanyProfile {
  name: string; tagline: string; about: string; mission: string
  website: string; email: string; phone: string; address: string
  founded: string; industry: string; logo_url: string
  social_links: Record<string, string>; extra_fields: Record<string, string>
}

interface Project {
  id: string; name: string; description: string; status: string
  folder_path: string; repository_url: string; deployment_url: string; tech_stack: string
  tags: string[]; created_at: string; updated_at: string
}

const statusStyle: Record<string, { bg: string; text: string; dot: string }> = {
  active: { bg: "bg-emerald-500/10 dark:bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400", dot: "bg-emerald-500" },
  in_development: { bg: "bg-amber-500/10 dark:bg-amber-500/10", text: "text-amber-600 dark:text-amber-400", dot: "bg-amber-500" },
  archived: { bg: "bg-zinc-500/10 dark:bg-zinc-500/10", text: "text-zinc-600 dark:text-zinc-400", dot: "bg-zinc-500" },
}

const statusLabels: Record<string, string> = {
  active: "Active", in_development: "In Development", archived: "Archived",
}

export default function CompanyPage() {
  const { user } = useAuth()
  const [profile, setProfile] = useState<CompanyProfile | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [actionMsg, setActionMsg] = useState("")
  const [actionType, setActionType] = useState<"ok" | "err">("ok")

  const [editingProject, setEditingProject] = useState<Project | null>(null)
  const [showProjectForm, setShowProjectForm] = useState(false)
  const [projectForm, setProjectForm] = useState({
    name: "", description: "", status: "active", folder_path: "", repository_url: "",
    deployment_url: "", tech_stack: "", tags: "",
  })
  const [savingProject, setSavingProject] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [activeTab, setActiveTab] = useState<"profile" | "projects" | "vps">("profile")
  const [vpsAccounts, setVpsAccounts] = useState<any[]>([])
  const [vpsForm, setVpsForm] = useState({
    name: "", vps_host: "", vps_port: "22", vps_username: "root",
    vps_private_key: "", vps_password: "",
  })
  const [editingVpsIndex, setEditingVpsIndex] = useState<number | null>(null)
  const [showVpsForm, setShowVpsForm] = useState(false)
  const [savingVps, setSavingVps] = useState(false)
  const [showVpsPassword, setShowVpsPassword] = useState(false)

  useEffect(() => { if (user) fetchData() }, [user?.id])

  const flash = (msg: string, type: "ok" | "err" = "ok") => {
    setActionMsg(msg); setActionType(type)
    setTimeout(() => setActionMsg(""), 4000)
  }

  const fetchData = async () => {
    const uid = user?.id ? `?user_id=${user.id}` : ""
    try {
      const [profRes, projRes, vpsRes] = await Promise.all([
        fetch(`${API}/api/company/profile${uid}`),
        fetch(`${API}/api/company/projects${uid}`),
        fetch(`${API}/api/company/vps-credentials${uid}`),
      ])
      const prof = await profRes.json()
      const proj = await projRes.json()
      setProfile(prof)
      setProjects(proj.projects || [])
      const vps = (await vpsRes.json()).vps_credentials || []
      setVpsAccounts(Array.isArray(vps) ? vps : [])
    } catch { flash("API is not reachable", "err") }
    setLoading(false)
  }

  const saveProfile = async () => {
    if (!profile) return
    setSaving(true)
    try {
      await fetch(`${API}/api/company/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...profile, user_id: user?.id || "" }),
      })
      flash("Company profile saved")
    } catch { flash("Failed to save profile", "err") }
    setSaving(false)
  }

  const openAddVps = () => {
    setEditingVpsIndex(null)
    setVpsForm({ name: "", vps_host: "", vps_port: "22", vps_username: "root", vps_private_key: "", vps_password: "" })
    setShowVpsForm(true)
  }

  const openEditVps = (idx: number) => {
    const a = vpsAccounts[idx] || {}
    setEditingVpsIndex(idx)
    setVpsForm({
      name: a.name || "",
      vps_host: a.vps_host || "",
      vps_port: a.vps_port || "22",
      vps_username: a.vps_username || "root",
      vps_private_key: a.vps_private_key || "",
      vps_password: a.vps_password || "",
    })
    setShowVpsForm(true)
  }

  const saveVpsAccount = async () => {
    if (!vpsForm.name.trim()) { flash("Account name is required", "err"); return }
    if (!vpsForm.vps_host.trim()) { flash("VPS host is required", "err"); return }
    setSavingVps(true)
    try {
      const body = { ...vpsForm, user_id: user?.id || "" }
      const url = `${API}/api/company/vps-credentials`
      const opts: RequestInit = {
        method: editingVpsIndex === null ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editingVpsIndex === null ? body : { ...body, index: editingVpsIndex, account: vpsForm }),
      }
      const res = await fetch(url, opts)
      const data = await res.json()
      if (data.vps_credentials) {
        setVpsAccounts(data.vps_credentials)
        setShowVpsForm(false)
        flash(editingVpsIndex === null ? "VPS account added" : "VPS account updated")
      } else {
        flash("Failed to save VPS account", "err")
      }
    } catch { flash("Failed to save VPS account", "err") }
    setSavingVps(false)
  }

  const deleteVpsAccount = async (idx: number) => {
    if (!confirm("Delete this VPS account?")) return
    try {
      const res = await fetch(`${API}/api/company/vps-credentials`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user?.id || "", index: idx }),
      })
      const data = await res.json()
      if (data.vps_credentials) setVpsAccounts(data.vps_credentials)
      flash("VPS account deleted")
    } catch { flash("Failed to delete VPS account", "err") }
  }

  const openAddProject = () => {
    setEditingProject(null)
    setProjectForm({ name: "", description: "", status: "active", folder_path: "", repository_url: "", deployment_url: "", tech_stack: "", tags: "" })
    setShowProjectForm(true)
  }

  const openEditProject = (p: Project) => {
    setEditingProject(p)
    setProjectForm({
      name: p.name, description: p.description, status: p.status,
      folder_path: p.folder_path, repository_url: p.repository_url, deployment_url: p.deployment_url,
      tech_stack: p.tech_stack, tags: p.tags.join(", "),
    })
    setShowProjectForm(true)
  }

  const saveProject = async () => {
    if (!projectForm.name.trim()) { flash("Project name is required", "err"); return }
    setSavingProject(true)
    const body = { ...projectForm, tags: projectForm.tags.split(",").map(t => t.trim()).filter(Boolean), user_id: user?.id || "" }
    try {
      if (editingProject) {
        await fetch(`${API}/api/company/projects/${editingProject.id}`, {
          method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        })
        flash("Project updated")
      } else {
        await fetch(`${API}/api/company/projects`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        })
        flash("Project added")
      }
      setShowProjectForm(false)
      fetchData()
    } catch { flash("Failed to save project", "err") }
    setSavingProject(false)
  }

  const deleteProject = async (id: string) => {
    if (!confirm("Delete this project?")) return
    try {
      await fetch(`${API}/api/company/projects/${id}?user_id=${user?.id || ""}`, { method: "DELETE" })
      flash("Project deleted")
      fetchData()
    } catch { flash("Failed to delete project", "err") }
  }

  const filteredProjects = projects.filter(p => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q) || p.tags.some(t => t.toLowerCase().includes(q))
  })

  const activeCount = projects.filter(p => p.status === "active").length
  const devCount = projects.filter(p => p.status === "in_development").length

  if (loading) return (
    <DashboardLayout>
      <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>
    </DashboardLayout>
  )

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-7xl">
        {/* Hero Header */}
        <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-primary/5 via-primary/10 to-transparent p-8">
          <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full -translate-y-1/2 translate-x-1/2 blur-3xl" />
          <div className="relative">
            <div className="flex items-center gap-3 mb-2">
              <div className="flex items-center justify-center h-12 w-12 rounded-xl bg-primary/10 border border-primary/20">
                <Building2 className="h-6 w-6 text-primary" />
              </div>
              <div>
                <h1 className="text-3xl font-bold tracking-tight">Layer 0</h1>
                <p className="text-muted-foreground text-sm">Company Information & Project Registry</p>
              </div>
            </div>
            <p className="text-muted-foreground mt-3 max-w-2xl">
              Manage your company profile and projects. The CEO agent reads from this layer to introduce your company and answer questions about projects.
            </p>
          </div>
        </div>

        {/* Flash message */}
        {actionMsg && (
          <div className={cn(
            "flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium transition-all",
            actionType === "ok"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
              : "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"
          )}>
            {actionType === "ok" ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            {actionMsg}
          </div>
        )}

        {/* Quick Stats */}
        <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
          {[
            { label: "Total Projects", value: projects.length, icon: Briefcase, color: "text-blue-500" },
            { label: "Active", value: activeCount, icon: Sparkles, color: "text-emerald-500" },
            { label: "In Development", value: devCount, icon: Target, color: "text-amber-500" },
            { label: "Company", value: profile?.name ? "Set" : "Not Set", icon: Users, color: "text-violet-500" },
          ].map((s) => (
            <div key={s.label} className="rounded-xl border border-border bg-card p-4 hover:border-border/80 transition-colors">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{s.label}</p>
                <s.icon className={cn("h-4 w-4", s.color)} />
              </div>
              <p className="text-2xl font-bold mt-1">{s.value}</p>
            </div>
          ))}
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-1 rounded-xl border border-border bg-muted/50 p-1 w-fit">
          {[
            { key: "profile" as const, label: "Company Profile", icon: Building2 },
            { key: "projects" as const, label: "Projects", icon: FolderOpen },
            { key: "vps" as const, label: "VPS Credentials", icon: Server },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all",
                activeTab === tab.key
                  ? "bg-background shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
              {tab.key === "projects" && (
                <span className="ml-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{projects.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* === COMPANY PROFILE TAB === */}
        {activeTab === "profile" && (
          <div className="space-y-6">
            {/* Profile Form */}
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="border-b border-border px-6 py-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Building2 className="h-5 w-5 text-primary" /> Company Information
                </h2>
                <p className="text-sm text-muted-foreground mt-0.5">Update your company details. The CEO uses this to introduce your company.</p>
              </div>
              <div className="p-6">
                <div className="grid gap-5 md:grid-cols-2">
                  {[
                    { key: "name", label: "Company Name", placeholder: "e.g. BritSync International", icon: Building2 },
                    { key: "tagline", label: "Tagline", placeholder: "e.g. Tech division of NobleRoot Ltd", icon: Sparkles },
                    { key: "founded", label: "Founded", placeholder: "e.g. October 2023", icon: Calendar },
                    { key: "industry", label: "Industry", placeholder: "e.g. AI Engineering", icon: Briefcase },
                    { key: "website", label: "Website", placeholder: "https://...", icon: Globe },
                    { key: "email", label: "Email", placeholder: "hello@company.com", icon: Mail },
                    { key: "phone", label: "Phone", placeholder: "+44 ...", icon: Phone },
                    { key: "address", label: "Address", placeholder: "London, UK", icon: MapPin },
                  ].map(f => (
                    <div key={f.key}>
                      <label className="text-sm font-medium text-foreground mb-1.5 flex items-center gap-1.5">
                        <f.icon className="h-3.5 w-3.5 text-muted-foreground" />
                        {f.label}
                      </label>
                      <input
                        className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                        placeholder={f.placeholder}
                        value={(profile as any)?.[f.key] || ""}
                        onChange={e => setProfile(p => p ? { ...p, [f.key]: e.target.value } : p)}
                      />
                    </div>
                  ))}
                </div>
                <div className="mt-5">
                  <label className="text-sm font-medium text-foreground mb-1.5 block">About</label>
                  <textarea
                    className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm min-h-[100px] focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors resize-none"
                    placeholder="What does this company do?"
                    value={profile?.about || ""}
                    onChange={e => setProfile(p => p ? { ...p, about: e.target.value } : p)}
                  />
                </div>
                <div className="mt-4">
                  <label className="text-sm font-medium text-foreground mb-1.5 block">Mission</label>
                  <textarea
                    className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm min-h-[80px] focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors resize-none"
                    placeholder="Company mission statement"
                    value={profile?.mission || ""}
                    onChange={e => setProfile(p => p ? { ...p, mission: e.target.value } : p)}
                  />
                </div>
                <div className="mt-6 flex justify-end">
                  <button
                    onClick={saveProfile}
                    disabled={saving}
                    className="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 flex items-center gap-2 transition-all shadow-sm shadow-primary/25"
                  >
                    {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    Save Profile
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* === VPS CREDENTIALS TAB === */}
        {activeTab === "vps" && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="border-b border-border px-6 py-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <Server className="h-5 w-5 text-primary" /> VPS Credentials
                  </h2>
                  <p className="text-sm text-muted-foreground mt-0.5">Save multiple named SSH server accounts. They are reused to pre-fill the VPS Deploy page.</p>
                </div>
                <button
                  onClick={openAddVps}
                  className="rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 flex items-center gap-2 shadow-sm shadow-primary/25 transition-all"
                >
                  <Plus className="h-4 w-4" /> Add Account
                </button>
              </div>
              <div className="p-6">
                <div className="flex items-center gap-2 mb-4 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-600 dark:text-amber-400">
                  <Lock className="h-4 w-4 shrink-0" />
                  Credentials are stored privately per user and never shown on the VPS Deploy history.
                </div>

                {vpsAccounts.length === 0 && !showVpsForm ? (
                  <div className="rounded-xl border border-dashed border-border p-10 text-center">
                    <Server className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                    <p className="text-lg font-medium text-muted-foreground">No VPS accounts yet</p>
                    <p className="text-sm text-muted-foreground/70 mt-1">Click "Add Account" to save your first SSH server.</p>
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2">
                    {vpsAccounts.map((a, idx) => (
                      <div key={idx} className="group rounded-xl border border-border bg-card hover:border-primary/30 transition-all">
                        <div className="p-4">
                          <div className="flex items-start justify-between gap-2 mb-3">
                            <div className="flex items-center gap-2">
                              <Server className="h-4 w-4 text-primary" />
                              <h3 className="font-semibold text-sm">{a.name || `VPS ${idx + 1}`}</h3>
                            </div>
                            <div className="flex items-center gap-1">
                              <button onClick={() => openEditVps(idx)} className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
                                <Edit3 className="h-4 w-4" />
                              </button>
                              <button onClick={() => deleteVpsAccount(idx)} className="rounded-md p-1.5 text-red-500 hover:bg-red-500/5 transition-colors">
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </div>
                          </div>
                          <div className="space-y-1.5 text-xs text-muted-foreground">
                            <div className="flex items-center gap-1.5"><Server className="h-3 w-3" /> {a.vps_host}{a.vps_port && `:${a.vps_port}`}</div>
                            <div className="flex items-center gap-1.5"><Users className="h-3 w-3" /> {a.vps_username}</div>
                            {(a.vps_private_key || a.vps_password) && (
                              <div className="flex items-center gap-1.5"><Lock className="h-3 w-3" /> {a.vps_private_key ? "SSH key" : a.vps_password ? "Password" : ""}</div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {showVpsForm && (
                  <div className="mt-6 rounded-xl border border-border bg-muted/30 p-5 space-y-4">
                    <h4 className="font-semibold text-sm flex items-center gap-2">
                      <KeyRound className="h-4 w-4 text-primary" /> {editingVpsIndex === null ? "Add VPS Account" : "Edit VPS Account"}
                    </h4>
                    <div className="grid gap-5 md:grid-cols-2">
                      <div>
                        <label className="text-sm font-medium text-foreground mb-1.5 flex items-center gap-1.5">
                          <Server className="h-3.5 w-3.5 text-muted-foreground" /> Account Name *
                        </label>
                        <input
                          className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                          placeholder="e.g. Production, Staging, Client A"
                          value={vpsForm.name}
                          onChange={e => setVpsForm(v => ({ ...v, name: e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="text-sm font-medium text-foreground mb-1.5 flex items-center gap-1.5">
                          <Server className="h-3.5 w-3.5 text-muted-foreground" /> VPS Host *
                        </label>
                        <input
                          className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                          placeholder="server.example.com"
                          value={vpsForm.vps_host}
                          onChange={e => setVpsForm(v => ({ ...v, vps_host: e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="text-sm font-medium text-foreground mb-1.5 flex items-center gap-1.5">
                          <KeyRound className="h-3.5 w-3.5 text-muted-foreground" /> Port
                        </label>
                        <input
                          className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                          placeholder="22"
                          value={vpsForm.vps_port}
                          onChange={e => setVpsForm(v => ({ ...v, vps_port: e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="text-sm font-medium text-foreground mb-1.5 flex items-center gap-1.5">
                          <Users className="h-3.5 w-3.5 text-muted-foreground" /> Username *
                        </label>
                        <input
                          className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                          placeholder="root"
                          value={vpsForm.vps_username}
                          onChange={e => setVpsForm(v => ({ ...v, vps_username: e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="text-sm font-medium text-foreground mb-1.5 flex items-center gap-1.5">
                          <KeyRound className="h-3.5 w-3.5 text-muted-foreground" /> SSH Password
                        </label>
                        <div className="relative">
                          <input
                            type={showVpsPassword ? "text" : "password"}
                            className="w-full rounded-lg border border-input bg-background px-3 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                            placeholder="SSH password (if no key)"
                            value={vpsForm.vps_password}
                            onChange={e => setVpsForm(v => ({ ...v, vps_password: e.target.value }))}
                          />
                          <button
                            type="button"
                            onClick={() => setShowVpsPassword(s => !s)}
                            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                            aria-label={showVpsPassword ? "Hide password" : "Show password"}
                          >
                            {showVpsPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-foreground mb-1.5 block flex items-center gap-1.5">
                        <Lock className="h-3.5 w-3.5 text-muted-foreground" /> SSH Private Key
                      </label>
                      <textarea
                        className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm min-h-[120px] focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors resize-none font-mono text-xs"
                        placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----"
                        value={vpsForm.vps_private_key}
                        onChange={e => setVpsForm(v => ({ ...v, vps_private_key: e.target.value }))}
                      />
                    </div>
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setShowVpsForm(false)}
                        className="rounded-lg border border-input bg-background px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={saveVpsAccount}
                        disabled={savingVps}
                        className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 flex items-center gap-2 transition-all shadow-sm shadow-primary/25"
                      >
                        {savingVps ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        {editingVpsIndex === null ? "Add Account" : "Update Account"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* === PROJECTS TAB === */}
        {activeTab === "projects" && (
          <div className="space-y-4">
            {/* Projects Header */}
            <div className="flex items-center justify-between">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  className="w-full rounded-lg border border-input bg-background pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                  placeholder="Search projects..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                />
              </div>
              <button
                onClick={openAddProject}
                className="rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 flex items-center gap-2 shadow-sm shadow-primary/25 transition-all"
              >
                <Plus className="h-4 w-4" /> Add Project
              </button>
            </div>

            {/* Projects Grid */}
            {filteredProjects.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border p-16 text-center">
                <FolderOpen className="h-16 w-16 mx-auto mb-4 text-muted-foreground/30" />
                <p className="text-lg font-medium text-muted-foreground">
                  {projects.length === 0 ? "No projects yet" : "No projects match your search"}
                </p>
                <p className="text-sm text-muted-foreground/70 mt-1">
                  {projects.length === 0 ? "Click Add Project to create your first project" : "Try a different search term"}
                </p>
                {projects.length === 0 && (
                  <button onClick={openAddProject} className="mt-4 rounded-lg bg-primary/10 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/20 transition-colors">
                    <Plus className="h-4 w-4 inline mr-1" /> Add Project
                  </button>
                )}
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {filteredProjects.map(p => {
                  const st = statusStyle[p.status] || statusStyle.active
                  return (
                    <div key={p.id} className="group rounded-2xl border border-border bg-card hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5 transition-all duration-200">
                      <div className="p-5">
                        <div className="flex items-start justify-between gap-2 mb-3">
                          <h3 className="font-semibold text-base group-hover:text-primary transition-colors">{p.name}</h3>
                          <span className={cn("flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium border", st.bg, st.text, "border-transparent")}>
                            <span className={cn("h-1.5 w-1.5 rounded-full", st.dot)} />
                            {statusLabels[p.status] || p.status}
                          </span>
                        </div>
                        {p.description && (
                          <p className="text-sm text-muted-foreground mb-4 line-clamp-2 leading-relaxed">{p.description}</p>
                        )}
                        <div className="space-y-2">
                          {p.tech_stack && (
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                              <Briefcase className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                              <span>{p.tech_stack}</span>
                            </div>
                          )}
                          {p.folder_path && (
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                              <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                              <span className="truncate" title={p.folder_path}>{p.folder_path}</span>
                            </div>
                          )}
                          {p.repository_url && (
                            <div className="flex items-center gap-2 text-xs">
                              <Link2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                              <a href={p.repository_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline truncate">{p.repository_url}</a>
                            </div>
                          )}
                          {p.deployment_url && (
                            <div className="flex items-center gap-2 text-xs">
                              <Globe className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                              <a href={p.deployment_url} target="_blank" rel="noopener" className="text-primary hover:underline truncate">{p.deployment_url}</a>
                            </div>
                          )}
                        </div>
                        {p.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-3">
                            {p.tags.map(t => (
                              <span key={t} className="rounded-md bg-secondary/80 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">{t}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center border-t border-border/50 divide-x divide-border/50">
                        <button onClick={() => openEditProject(p)} className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors">
                          <Edit3 className="h-3.5 w-3.5" /> Edit
                        </button>
                        {p.deployment_url && (
                          <a href={p.deployment_url} target="_blank" rel="noopener" className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors">
                            <ExternalLink className="h-3.5 w-3.5" /> Live
                          </a>
                        )}
                        <button onClick={() => deleteProject(p.id)} className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium text-red-500 hover:bg-red-500/5 transition-colors">
                          <Trash2 className="h-3.5 w-3.5" /> Delete
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* === PROJECT FORM MODAL === */}
        {showProjectForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 dark:bg-black/60 backdrop-blur-sm" onClick={() => setShowProjectForm(false)}>
            <div className="bg-card border border-border rounded-2xl p-6 w-full max-w-lg shadow-2xl mx-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-5 shrink-0">
                <h3 className="text-lg font-semibold">{editingProject ? "Edit Project" : "Add Project"}</h3>
                <button onClick={() => setShowProjectForm(false)} className="rounded-lg p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="space-y-4 overflow-y-auto flex-1 min-h-0 pr-1">
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">Project Name *</label>
                  <input className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                    placeholder="e.g. LeadHunter" value={projectForm.name}
                    onChange={e => setProjectForm(f => ({ ...f, name: e.target.value }))} />
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">Description</label>
                  <textarea className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm min-h-[90px] focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors resize-none"
                    placeholder="What is this project about?" value={projectForm.description}
                    onChange={e => setProjectForm(f => ({ ...f, description: e.target.value }))} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">Status</label>
                    <select className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                      value={projectForm.status}
                      onChange={e => setProjectForm(f => ({ ...f, status: e.target.value }))}>
                      <option value="active">Active</option>
                      <option value="in_development">In Development</option>
                      <option value="archived">Archived</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">Tech Stack</label>
                    <input className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                      placeholder="Next.js, Python..." value={projectForm.tech_stack}
                      onChange={e => setProjectForm(f => ({ ...f, tech_stack: e.target.value }))} />
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">GitHub Repository URL</label>
                  <div className="flex gap-2">
                    <input className="flex-1 rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                      placeholder="https://github.com/user/repo" value={projectForm.repository_url}
                      onChange={e => setProjectForm(f => ({ ...f, repository_url: e.target.value }))} />
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-1.5">Paste the GitHub URL of this project so the team can access its source code.</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">Deployment URL</label>
                  <input className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                    placeholder="https://leadhunter.example.com" value={projectForm.deployment_url}
                    onChange={e => setProjectForm(f => ({ ...f, deployment_url: e.target.value }))} />
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">Tags</label>
                  <input className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50 focus:border-primary/50 transition-colors"
                    placeholder="lead-gen, email, automation (comma separated)" value={projectForm.tags}
                    onChange={e => setProjectForm(f => ({ ...f, tags: e.target.value }))} />
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-border shrink-0">
                <button onClick={() => setShowProjectForm(false)} className="rounded-lg border border-input bg-background px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">Cancel</button>
                <button onClick={saveProject} disabled={savingProject}
                  className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 flex items-center gap-2 shadow-sm shadow-primary/25 transition-all">
                  {savingProject ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {editingProject ? "Update" : "Create"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
