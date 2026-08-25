"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  SwatchBook,
  Palette,
  Loader2,
  Send,
  Scale,
  CheckCircle2,
  RefreshCw,
  ExternalLink,
  FileDown,
  Layers,
  FileSearch,
  Crosshair,
  Paintbrush,
  Sparkles,
  Crown,
} from "lucide-react"

const API = "http://127.0.0.1:8001"

const SUBJECT_TYPES = [
  { id: "screen", label: "Screen" },
  { id: "component", label: "Component" },
  { id: "flow", label: "Flow" },
  { id: "whole_product", label: "Whole Product" },
  { id: "brand", label: "Brand Identity" },
]

interface Dept {
  id: string
  name: string
  title: string
  order: number
  is_coordinator: boolean
}

interface DesignStats {
  total: number
  in_progress: number
  completed: number
  failed: number
  avg_confidence: number | null
  avg_visual_quality: number | null
  total_components: number
  total_tokens: number
  departments: number
}

interface PackageSummary {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  avg_confidence: number | null
  visual_quality_score: number | null
  total_components: number
  total_tokens: number
  departments_completed: number
  total_departments: number
  board_review_id: string | null
}

interface DeptReport {
  department_id: string
  department_name: string
  department_title: string
  verdict: string
  confidence: number
  score: number | null
  tokens: string[]
  components: string[]
  findings: string[]
  recommendations: string[]
  evidence: string[]
  status: string
  error: string
}

interface PackageDetail {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  completed_at: string | null
  reports: DeptReport[]
  visual_quality_score: number | null
  design_components: string[]
  layout_specification: string[]
  spacing_rules: string[]
  typography: string[]
  color_tokens: string[]
  icon_selection: string[]
  responsive_behavior: string[]
  animation_rules: string[]
  accessibility_requirements: string[]
  component_variants: string[]
  design_assets: string[]
  acceptance_checklist: string[]
  visual_specification: string
  executive_summary: string
  avg_confidence: number | null
  total_components: number
  total_tokens: number
  board_review_id: string | null
  error: string
}

const verdictStyle: Record<string, string> = {
  support: "bg-green-500/10 text-green-500 border-green-500/30",
  recommend: "bg-blue-500/10 text-blue-500 border-blue-500/30",
  caution: "bg-amber-500/10 text-amber-500 border-amber-500/30",
  risk: "bg-red-500/10 text-red-500 border-red-500/30",
  neutral: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
}

const statusStyle: Record<string, string> = {
  completed: "bg-green-500/10 text-green-500 border-green-500/30",
  in_progress: "bg-blue-500/10 text-blue-500 border-blue-500/30",
  failed: "bg-red-500/10 text-red-500 border-red-500/30",
  cancelled: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
}

function scoreColor(score: number): string {
  if (score >= 70) return "text-green-500"
  if (score >= 50) return "text-amber-500"
  return "text-red-500"
}

function hexFromToken(token: string): string | null {
  const m = token.match(/#[0-9a-fA-F]{3,8}\b/)
  return m ? m[0] : null
}

export default function DesignPage() {
  const [stats, setStats] = useState<DesignStats | null>(null)
  const [departments, setDepartments] = useState<Dept[]>([])
  const [packages, setPackages] = useState<PackageSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [apiDown, setApiDown] = useState(false)

  const [requestText, setRequestText] = useState("")
  const [subjectType, setSubjectType] = useState("screen")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<PackageDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [sending, setSending] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState("")

  const fetchOverview = () => {
    Promise.all([
      fetch(`${API}/api/design/stats`).then((r) => r.json()),
      fetch(`${API}/api/design/departments`).then((r) => r.json()),
      fetch(`${API}/api/design/packages`).then((r) => r.json()),
    ])
      .then(([statsData, deptData, packageData]) => {
        setStats(statsData || null)
        setDepartments(deptData.departments || [])
        setPackages(packageData.packages || [])
        setLoading(false)
        setApiDown(false)
      })
      .catch(() => {
        setLoading(false)
        setApiDown(true)
      })
  }

  useEffect(() => { fetchOverview() }, [])

  const submitDesign = () => {
    if (!requestText.trim()) return
    setSubmitting(true)
    setSubmitError("")
    setLastAction("")
    fetch(`${API}/api/design/packages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: requestText.trim(), subject_type: subjectType, wait: false }),
    })
      .then((r) => r.json())
      .then(async (data) => {
        if (data.error) throw new Error(data.error)
        const packageId = data.package_id || (data.package && data.package.id)
        if (!packageId) throw new Error("No package id returned")
        await pollUntilDone(packageId)
        setRequestText("")
        fetchOverview()
      })
      .catch((e) => setSubmitError(e.message || "Submission failed"))
      .finally(() => setSubmitting(false))
  }

  const pollUntilDone = (packageId: string, attempts = 0): Promise<void> => {
    return fetch(`${API}/api/design/packages/${packageId}`)
      .then((r) => r.json())
      .then((data) => {
        const packageDetail = data.package
        if (packageDetail && (packageDetail.status === "completed" || packageDetail.status === "failed" || packageDetail.status === "cancelled")) {
          setLastAction(`Visual Design Package finished: ${packageDetail.status}`)
          return
        }
        if (packageDetail && attempts % 15 === 0) {
          setLastAction(`Design in progress: ${packageDetail.departments_completed}/${packageDetail.total_departments} departments (${packageDetail.stage})`)
        }
        if (attempts > 7200) throw new Error("Timed out waiting for Visual Design Package")
        return new Promise((resolve) => setTimeout(resolve, 2000)).then(() =>
          pollUntilDone(packageId, attempts + 1)
        )
      })
  }

  const toggleDetail = (id: string) => {
    if (expandedId === id) {
      setExpandedId(null)
      setDetail(null)
      return
    }
    setExpandedId(id)
    setDetailLoading(true)
    fetch(`${API}/api/design/packages/${id}`)
      .then((r) => r.json())
      .then((data) => setDetail(data.package))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }

  const sendToBoard = (id: string) => {
    setSending(id)
    setLastAction("")
    fetch(`${API}/api/design/packages/${id}/to-board`, { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error)
        setLastAction(`Sent to Executive Product Board for review (review ${data.board_review_id?.slice(0, 8)})`)
        fetchOverview()
      })
      .catch((e) => setLastAction(`Send to board failed: ${e.message}`))
      .finally(() => setSending(null))
  }

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading Visual Design division...</p>
        </div>
      </DashboardLayout>
    )
  }

  if (apiDown) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <p className="text-xl font-semibold mb-2">API Server Not Running</p>
            <p className="text-muted-foreground">
              Start the API: <code className="bg-secondary px-1 rounded">py -m apps.api.main</code>
            </p>
          </div>
        </div>
      </DashboardLayout>
    )
  }

  const sectionBlock = (title: string, items: string[]) =>
    items.length > 0 && (
      <div>
        <h4 className="text-sm font-semibold mb-1.5">{title}</h4>
        <ul className="space-y-1">
          {items.map((item, i) => (
            <li key={i} className="text-xs text-muted-foreground">{item}</li>
          ))}
        </ul>
      </div>
    )

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
              <SwatchBook className="h-8 w-8 text-primary" />
              Visual Design &amp; Design System
              <span className="text-sm font-medium text-muted-foreground bg-secondary/60 rounded-full px-3 py-1">Layer 5</span>
            </h1>
            <p className="text-muted-foreground mt-1">
              Twelve departments define the unified visual language - design system, brand identity, components,
              layout, hierarchy, icons, illustrations, motion, responsive behavior, themes, and Design QA. The
              Creative Director merges everything into a Visual Design Package the Frontend Development Agent
              implements exactly. This division defines visuals; it never writes code.
            </p>
          </div>
          <button
            onClick={fetchOverview}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground hover:bg-secondary shrink-0"
          >
            <RefreshCw className="h-4 w-4 inline mr-1" /> Refresh
          </button>
        </div>

        {lastAction && (
          <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-sm text-primary">
            {lastAction}
          </div>
        )}

        {/* Stats */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Design Packages</p>
            <p className="text-3xl font-bold mt-1">{stats?.total || 0}</p>
            <p className="text-xs text-muted-foreground">{stats?.in_progress || 0} in progress</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" /> Completed
            </p>
            <p className="text-3xl font-bold mt-1 text-green-500">{stats?.completed || 0}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <Scale className="h-3.5 w-3.5 text-primary" /> Avg Visual Quality
            </p>
            <p className={`text-3xl font-bold mt-1 ${stats?.avg_visual_quality != null ? scoreColor(stats.avg_visual_quality) : ""}`}>
              {stats?.avg_visual_quality != null ? `${stats.avg_visual_quality}/100` : "—"}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Tokens &amp; Components</p>
            <p className="text-3xl font-bold mt-1">{stats?.total_tokens || 0}</p>
            <p className="text-xs text-muted-foreground">{stats?.total_components || 0} reusable components</p>
          </div>
        </div>

        {/* Submit subject */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Send className="h-5 w-5 text-primary" /> Request Visual Design Package
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Describe the design subject. All twelve design departments specify it, then the Creative Director
            writes one package with design tokens, components, and an implementation-ready visual specification
            for the Frontend Development Agent.
          </p>
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              {SUBJECT_TYPES.map((st) => (
                <button
                  key={st.id}
                  onClick={() => setSubjectType(st.id)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                    subjectType === st.id
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border bg-background text-muted-foreground hover:bg-secondary"
                  }`}
                >
                  {st.label}
                </button>
              ))}
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <textarea
                value={requestText}
                onChange={(e) => setRequestText(e.target.value)}
                placeholder="e.g. Create a CRM dashboard. Use the approved dashboard components, the desktop grid, summary cards, a pipeline chart, and an activity table. Support light and dark mode..."
                rows={2}
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <button
                onClick={submitDesign}
                disabled={submitting || !requestText.trim()}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 self-end"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Run Design Package"}
              </button>
            </div>
          </div>
          {submitError && <p className="mt-2 text-sm text-red-500">{submitError}</p>}
          {submitting && (
            <p className="mt-3 text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Twelve design departments are specifying (this can take a few minutes)...
            </p>
          )}
        </div>

        {/* Department roster */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" /> Design Departments
          </h2>
          <p className="text-sm text-muted-foreground mb-4">The twelve departments that define and validate the visual language.</p>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {departments.map((dept) => (
              <div key={dept.id} className="rounded-lg border border-border/50 bg-background/50 p-4">
                <div className="flex items-center gap-3">
                  <div className={`rounded-lg p-2 ${dept.is_coordinator ? "bg-amber-500/10" : "bg-primary/10"}`}>
                    {dept.is_coordinator ? (
                      <Crown className="h-4 w-4 text-amber-500" />
                    ) : (
                      <Palette className="h-4 w-4 text-primary" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{dept.name}</p>
                    {dept.is_coordinator && <p className="text-xs text-amber-500">Merges specs into the package + visual spec</p>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Packages */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-primary" /> Visual Design Packages
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Every Visual Design Package the division has produced.</p>
          {packages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No packages yet. Request a Visual Design Package above.</p>
          ) : (
            <div className="space-y-2">
              {packages.map((pkg) => (
                <div key={pkg.id} className="rounded-lg border border-border/50 bg-background/50">
                  <button
                    onClick={() => toggleDetail(pkg.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-secondary/40 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold truncate">{pkg.request}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(pkg.created_at).toLocaleString()} · {pkg.departments_completed}/{pkg.total_departments} departments ·{" "}
                        {SUBJECT_TYPES.find((s) => s.id === pkg.subject_type)?.label || pkg.subject_type}
                      </p>
                    </div>
                    {pkg.visual_quality_score != null && (
                      <span className={`text-xs font-bold ${scoreColor(pkg.visual_quality_score)}`}>
                        {pkg.visual_quality_score}/100
                      </span>
                    )}
                    <span
                      className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${statusStyle[pkg.status] || "border-border bg-secondary/60 text-muted-foreground"}`}
                    >
                      {pkg.status}
                    </span>
                  </button>

                  {expandedId === pkg.id && (
                    <div className="border-t border-border/50 px-4 py-4">
                      {detailLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                          <Loader2 className="h-4 w-4 animate-spin" /> Loading package...
                        </div>
                      ) : detail ? (
                        <div className="space-y-4">
                          {detail.error && <p className="text-sm text-red-500">Error: {detail.error}</p>}

                          {detail.visual_quality_score != null && (
                            <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 flex items-center gap-4">
                              <div>
                                <p className="text-sm text-muted-foreground">Visual Quality Score</p>
                                <p className={`text-3xl font-bold ${scoreColor(detail.visual_quality_score)}`}>{detail.visual_quality_score}/100</p>
                              </div>
                              <p className="text-sm text-muted-foreground flex-1">
                                {detail.executive_summary || "Visual Design Package completed. See the specification for what to build."}
                              </p>
                            </div>
                          )}

                          {/* Department reports */}
                          <div>
                            <h3 className="text-sm font-semibold mb-2">Department Reports</h3>
                            <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                              {detail.reports.map((r) => (
                                <div key={r.department_id} className="rounded-lg border border-border/50 bg-background/60 p-3">
                                  <div className="flex items-center justify-between gap-2">
                                    <p className="text-xs font-semibold truncate">{r.department_name}</p>
                                    {r.status === "completed" ? (
                                      <span className={`rounded-full border px-1.5 py-0.5 text-[10px] capitalize shrink-0 ${verdictStyle[r.verdict] || verdictStyle.neutral}`}>
                                        {r.verdict}
                                      </span>
                                    ) : null}
                                  </div>
                                  <p className="text-xs text-muted-foreground mt-0.5">
                                    {r.status === "completed"
                                      ? `${r.score != null ? `${r.score}/100 · ` : ""}${Math.round(r.confidence * 100)}% confidence · ${r.tokens.length} tokens · ${r.components.length} components`
                                      : r.status}
                                  </p>
                                  {r.status === "failed" && r.error && (
                                    <p className="text-xs text-red-500 mt-1" title={r.error}>{r.error}</p>
                                  )}
                                  {r.status === "completed" && r.components.length > 0 && (
                                    <ul className="mt-1.5 space-y-0.5">
                                      {r.components.slice(0, 3).map((c, i) => (
                                        <li key={i} className="text-xs text-muted-foreground">- {c}</li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Color token swatches */}
                          {detail.color_tokens.length > 0 && (
                            <div>
                              <h4 className="text-sm font-semibold mb-1.5">Color Tokens</h4>
                              <div className="flex flex-wrap gap-2">
                                {detail.color_tokens.slice(0, 16).map((t, i) => {
                                  const hex = hexFromToken(t)
                                  return (
                                    <div key={i} className="flex items-center gap-2 rounded-lg border border-border/50 bg-background/60 px-2.5 py-1.5">
                                      {hex && (
                                        <span
                                          className="h-4 w-4 rounded border border-border"
                                          style={{ backgroundColor: hex }}
                                        />
                                      )}
                                      <span className="text-xs text-muted-foreground">{t}</span>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          )}

                          {/* Package sections */}
                          <div className="grid gap-4 md:grid-cols-2">
                            {sectionBlock("Design System Components", detail.design_components)}
                            {sectionBlock("Layout Specification", detail.layout_specification)}
                            {sectionBlock("Spacing Rules", detail.spacing_rules)}
                            {sectionBlock("Typography", detail.typography)}
                            {sectionBlock("Icon Selection", detail.icon_selection)}
                            {sectionBlock("Responsive Behavior", detail.responsive_behavior)}
                            {sectionBlock("Animation Rules", detail.animation_rules)}
                            {sectionBlock("Accessibility Requirements", detail.accessibility_requirements)}
                            {sectionBlock("Component Variants", detail.component_variants)}
                            {sectionBlock("Design Assets", detail.design_assets)}
                            {sectionBlock("Acceptance Checklist", detail.acceptance_checklist)}
                          </div>

                          {detail.visual_specification && (
                            <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
                              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                                <Sparkles className="h-4 w-4" /> Implementation-Ready Visual Specification
                              </h3>
                              <pre className="text-xs whitespace-pre-wrap font-sans text-muted-foreground max-h-96 overflow-y-auto">
                                {detail.visual_specification}
                              </pre>
                            </div>
                          )}

                          {!detail.visual_specification && detail.executive_summary && (
                            <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
                              <h3 className="text-sm font-semibold mb-1">Executive Summary</h3>
                              <p className="text-sm text-muted-foreground">{detail.executive_summary}</p>
                            </div>
                          )}

                          {/* Actions */}
                          <div className="flex flex-wrap gap-2 pt-1">
                            {pkg.status === "completed" && (
                              <button
                                onClick={() => sendToBoard(pkg.id)}
                                disabled={sending === pkg.id || detail.board_review_id != null}
                                className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                              >
                                {sending === pkg.id ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <ExternalLink className="h-3.5 w-3.5 inline mr-1" />
                                )}
                                {detail.board_review_id ? "Sent to Board" : "Send to Board"}
                              </button>
                            )}
                            <a
                              href={`${API}/api/design/packages/${pkg.id}/export`}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary"
                            >
                              <FileDown className="h-3.5 w-3.5 inline mr-1" /> Export
                            </a>
                          </div>
                        </div>
                      ) : (
                        <p className="text-sm text-red-500">Failed to load package detail.</p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Paintbrush className="h-4 w-4" />
          The Visual Design Division never writes frontend code - it delivers an implementation-ready
          Visual Design Package that the Frontend Development Agent builds exactly as defined. No custom
          components unless approved by the Design System Department.
        </div>
      </div>
    </DashboardLayout>
  )
}
